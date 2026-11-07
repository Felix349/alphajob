"""简历：保存、读取，以及从 PDF 中提取文本。"""

import asyncio
import re

import pymupdf
import pymupdf4llm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Resume, User
from app.models.resume import ResumeLanguage
from app.schemas.resume import MAX_RESUME_CHARS

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# 提取出的文字少于这个长度，基本可以判断是扫描件（整页都是图片）
MIN_TEXT_CHARS = 50


class ResumeParseError(Exception):
    pass


async def get_resume(
    db: AsyncSession, user: User, language: ResumeLanguage = "zh"
) -> Resume | None:
    stmt = select(Resume).where(Resume.user_id == user.id, Resume.language == language)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_resumes(db: AsyncSession, user: User) -> dict[str, Resume]:
    """当前用户的所有简历，按语言索引：{"zh": ..., "en": ...}"""
    rows = (await db.execute(select(Resume).where(Resume.user_id == user.id))).scalars()
    return {r.language: r for r in rows}


async def save_resume(
    db: AsyncSession,
    user: User,
    content_md: str,
    *,
    language: ResumeLanguage = "zh",
    source: str = "manual",
    filename=None,
) -> Resume:
    resume = await get_resume(db, user, language)
    if resume is None:
        resume = Resume(
            user_id=user.id,
            language=language,
            content_md=content_md,
            source=source,
            filename=filename,
        )
        db.add(resume)
    else:
        resume.content_md = content_md
        resume.source = source
        if filename is not None:
            resume.filename = filename
    await db.commit()
    await db.refresh(resume)
    return resume


async def delete_resume(db: AsyncSession, user: User, language: ResumeLanguage = "zh") -> bool:
    resume = await get_resume(db, user, language)
    if resume is None:
        return False
    await db.delete(resume)
    await db.commit()
    return True


# 汉字、日韩文字和全角标点。用来判断“换行处两边是不是中文”
_CJK = r"　-〿㐀-䶿一-鿿豈-﫿＀-￯"
_CJK_AT_END = re.compile(f"[{_CJK}]$")
_CJK_AT_START = re.compile(f"^[{_CJK}]")
# 拼接处前后各取几个字作为“定位锚点”，足够长才不会误伤正文里别处的相同片段
_ANCHOR = 4


def _fix_cjk_line_joins(markdown: str, doc) -> str:
    """去掉 PDF 换行处被多加的空格。

    PDF 里没有“段落”，只有一行一行的文字。pymupdf4llm 把同一段的多行拼起来时，
    行与行之间统一加一个空格：英文需要这个空格，中文不需要，于是出现“向量 库”这样的断裂。

    不能简单地“删掉所有汉字之间的空格”：简历里本来就常用空格分隔，比如“某某大学 计算机科学 硕士”。
    所以这里先从 PDF 拿到真实的换行位置，只修复“换行处、两边都是中文”的那个空格。
    找不到对应片段时（比如被加了粗体标记）就不改，宁可漏修也不误改。
    """
    for page in doc:
        lines = [ln.strip() for ln in page.get_text().splitlines() if ln.strip()]
        for prev, nxt in zip(lines, lines[1:], strict=False):
            if _CJK_AT_END.search(prev) and _CJK_AT_START.search(nxt):
                tail, head = prev[-_ANCHOR:], nxt[:_ANCHOR]
                markdown = markdown.replace(f"{tail} {head}", f"{tail}{head}", 1)
    return markdown


def _pdf_to_markdown(data: bytes) -> str:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF 对损坏文件抛出的异常类型不固定
        raise ResumeParseError("无法打开这个 PDF，文件可能已损坏") from exc
    with doc:
        if doc.needs_pass:
            raise ResumeParseError("PDF 设置了密码，请先取消密码再上传")
        try:
            # 转成 Markdown 能保留标题层级；不做 OCR（扫描件直接提示用户改为粘贴文本）
            text = pymupdf4llm.to_markdown(doc, use_ocr=False)
            text = _fix_cjk_line_joins(text, doc)
        except Exception:
            # 退回纯文本：get_text 保留了原始换行，中文不会被多加空格
            text = "\n".join(page.get_text() for page in doc)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < MIN_TEXT_CHARS:
        raise ResumeParseError("没能从 PDF 中提取到文字，可能是扫描件或图片。请直接粘贴简历文本")
    return text[:MAX_RESUME_CHARS]


async def extract_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ResumeParseError("文件不能超过 5 MB")
    name = filename.lower()
    if name.endswith(".pdf"):
        # PDF 解析是 CPU 密集的同步操作，放到线程里执行，不阻塞其他请求
        return await asyncio.to_thread(_pdf_to_markdown, data)
    if name.endswith((".md", ".markdown", ".txt")):
        try:
            text = data.decode("utf-8-sig").strip()
        except UnicodeDecodeError as exc:
            raise ResumeParseError("文本文件需要是 UTF-8 编码") from exc
        if len(text) < MIN_TEXT_CHARS:
            raise ResumeParseError("文件内容太短")
        return text[:MAX_RESUME_CHARS]
    raise ResumeParseError("只支持 PDF、Markdown（.md）或纯文本（.txt）文件")
