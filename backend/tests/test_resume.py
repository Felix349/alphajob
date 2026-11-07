import pymupdf
import pytest

RESUME_MD = "# 张三\n\n## 教育经历\n某某大学 计算机科学 硕士\n\n## 技能\nPython、PyTorch、LangGraph"


def make_pdf(lines: list[str]) -> bytes:
    """用 PyMuPDF 现场生成一个带中文的 PDF，避免在仓库里放二进制测试文件。"""
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 80 + i * 20), line, fontname="china-s", fontsize=11)
    return doc.tobytes()


@pytest.fixture
async def alice(user_client):
    return await user_client("alice@example.com")


async def upload(client, filename: str, data: bytes, mime="application/octet-stream"):
    return await client.post("/api/resume/upload", files={"file": (filename, data, mime)})


async def test_no_resume_is_null_not_404(alice):
    resp = await alice.get("/api/resume")
    assert resp.status_code == 200 and resp.json() is None


async def test_save_and_update_markdown(alice):
    first = (await alice.put("/api/resume", json={"content_md": RESUME_MD})).json()
    assert first["source"] == "manual" and "LangGraph" in first["content_md"]
    second = (await alice.put("/api/resume", json={"content_md": RESUME_MD + "\nRust"})).json()
    assert second["id"] == first["id"]  # 每个用户只有一份简历：更新而不是新建
    assert second["updated_at"] > first["updated_at"]
    assert (await alice.get("/api/resume")).json()["content_md"].endswith("Rust")


async def test_rejects_too_short_resume(alice):
    assert (await alice.put("/api/resume", json={"content_md": "太短"})).status_code == 422


async def test_upload_pdf_extracts_chinese_text(alice):
    pdf = make_pdf(
        [
            "张三 · AI 研究方向",
            "教育经历：某某大学 计算机科学 硕士",
            "技能：Python、PyTorch、LangGraph、RAG",
        ]
    )
    resp = await upload(alice, "张三-简历.pdf", pdf, "application/pdf")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "pdf" and body["filename"] == "张三-简历.pdf"
    assert "张三" in body["content_md"] and "LangGraph" in body["content_md"]


async def test_upload_markdown_file(alice):
    resp = await upload(alice, "resume.md", RESUME_MD.encode("utf-8"), "text/markdown")
    assert resp.status_code == 200 and resp.json()["content_md"].startswith("# 张三")


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [
        ("resume.docx", b"PK\x03\x04", "只支持"),
        ("broken.pdf", b"%PDF-1.4 not really a pdf", "无法打开"),
        ("scan.pdf", None, "扫描件"),  # 没有文字的 PDF，相当于扫描件
        ("huge.pdf", b"0" * (5 * 1024 * 1024 + 10), "5 MB"),
        ("gbk.txt", "张三的简历，熟悉 Python 与 PyTorch。".encode("gbk") * 5, "UTF-8"),
    ],
)
async def test_upload_rejects_bad_files(alice, filename, data, message):
    if data is None:
        doc = pymupdf.open()
        doc.new_page()
        data = doc.tobytes()
    resp = await upload(alice, filename, data)
    assert resp.status_code == 422
    assert message in resp.json()["detail"]
    assert (await alice.get("/api/resume")).json() is None  # 失败时什么都不保存


async def test_resume_is_private(alice, user_client):
    await alice.put("/api/resume", json={"content_md": RESUME_MD})
    bob = await user_client("bob@example.com")
    assert (await bob.get("/api/resume")).json() is None


async def test_delete_resume(alice):
    await alice.put("/api/resume", json={"content_md": RESUME_MD})
    assert (await alice.delete("/api/resume")).status_code == 204
    assert (await alice.get("/api/resume")).json() is None


EN_RESUME_MD = (
    "# Zhang San\n\n## Education\nM.S. in Computer Science\n\n## Skills\nPython, LangGraph"
)


async def test_chinese_and_english_resumes_are_separate_slots(alice):
    zh = (await alice.put("/api/resume", json={"content_md": RESUME_MD})).json()
    en = (await alice.put("/api/resume?language=en", json={"content_md": EN_RESUME_MD})).json()
    assert zh["language"] == "zh" and en["language"] == "en" and zh["id"] != en["id"]

    assert (await alice.get("/api/resume")).json()["content_md"].startswith("# 张三")
    assert (await alice.get("/api/resume?language=en")).json()["content_md"].startswith("# Zhang")

    # 删掉英文简历，中文简历不受影响
    assert (await alice.delete("/api/resume?language=en")).status_code == 204
    assert (await alice.get("/api/resume?language=en")).json() is None
    assert (await alice.get("/api/resume")).json()["id"] == zh["id"]


async def test_upload_into_english_slot(alice):
    resp = await alice.post(
        "/api/resume/upload?language=en",
        files={"file": ("resume-en.md", EN_RESUME_MD.encode("utf-8"), "text/markdown")},
    )
    assert resp.status_code == 200 and resp.json()["language"] == "en"
    assert (await alice.get("/api/resume")).json() is None  # 中文栏位仍然是空的


async def test_rejects_unknown_language(alice):
    resp = await alice.put("/api/resume?language=fr", json={"content_md": RESUME_MD})
    assert resp.status_code == 422


async def test_pdf_line_wraps_do_not_insert_spaces_into_chinese(alice):
    """PDF 换行处不应在中文之间多出空格，但行内原有的空格（如“大学 专业 学历”）要保留。"""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), "某某大学 计算机科学 硕士", fontname="china-s", fontsize=11)
    paragraph = (
        "基于这套工具，我在迭代中系统性修复了向量库ID错位、Markdown 表格被切断、"
        "路由关键词误判、百分比字段类型错误等问题，显著提升了系统的可靠性与可维护性。"
    )
    # 窄文本框：强制把一段话折成很多行
    page.insert_textbox(pymupdf.Rect(72, 90, 300, 400), paragraph, fontname="china-s", fontsize=11)
    resp = await upload(alice, "wrap.pdf", doc.tobytes(), "application/pdf")
    text = resp.json()["content_md"]
    for joined in ["修复了向量库ID错位", "百分比字段类型错误", "可靠性与可维护性"]:
        assert joined in text, text
    assert "某某大学 计算机科学 硕士" in text  # 原有空格保留
