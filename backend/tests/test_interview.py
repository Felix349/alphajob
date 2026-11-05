"""面试复盘：状态机、语音与文字两种输入、失败与重试、题库筛选。

大模型和语音识别都用假实现；后台任务用“立即执行”的队列代替 Redis + Worker。
只有音频格式转换（ffmpeg）是真实运行的。
"""

import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest
from sqlalchemy import func, select

from app.asr import TranscribeError, TranscriptResult
from app.asr.dashscope_asr import to_wav_16k
from app.llm import LLMError, StructuredResult
from app.main import app
from app.models import LLMCallLog, WeakPoint
from app.schemas.interview import InterviewAnalysis
from app.services.interview_pipeline import process_interview
from app.storage import LocalStorage, get_storage
from app.tasks import QueueUnavailable, get_task_queue
from tests.conftest import TestSessionLocal

RECALL = (
    "今天是北辰云一面。先自我介绍，然后问论文助手的长期记忆怎么设计，我说用向量库，但淘汰策略没讲清楚。"
    "第二题手写 LRU 缓存，我用哈希表加双向链表写出来了。最后问 Agent 评测方法，我只说了任务成功率。"
)

ANALYSIS = InterviewAnalysis.model_validate(
    {
        "questions": [
            {
                "question": "长期记忆怎么设计？",
                "my_answer": "用向量库存储",
                "score": 2,
                "feedback": "淘汰策略没讲",
                "improved_answer": "先说分层记忆……",
                "tags": ["Agent 记忆"],
            },
            {
                "question": "手写 LRU 缓存",
                "my_answer": "哈希表加双向链表",
                "score": 4,
                "feedback": "思路正确",
                "improved_answer": "O(1) 的关键是……",
                "tags": ["缓存", "数据结构"],
            },
            {
                "question": "Agent 评测有哪些方法？",
                "my_answer": "任务成功率",
                "score": 2,
                "feedback": "维度太少",
                "improved_answer": "从结果、过程、成本三方面……",
                "tags": ["Agent 评测"],
            },
        ],
        "summary": "考察 Agent 基础与编码，评测方法是短板。",
        "highlights": ["LRU 写得完整"],
        "weak_points": [{"topic": "Agent 评测方法", "detail": "只知道任务成功率"}],
        "next_round_advice": ["整理 Agent 评测指标体系"],
    }
)


class FakeLLM:
    provider, model = "fake", "fake-model"

    def __init__(self, error: Exception | None = None):
        self.error, self.prompts = error, []

    async def structured(self, *, system, user, schema, effort="medium", max_tokens=4096):
        self.prompts.append(user)
        if self.error:
            raise self.error
        return StructuredResult(ANALYSIS, "fake", "fake-model", 800, 600)


class FakeTranscriber:
    name = "fake"

    def __init__(self, error: Exception | None = None):
        self.error, self.calls = error, []

    async def transcribe(self, path: Path) -> TranscriptResult:
        self.calls.append(path)
        if self.error:
            raise self.error
        assert path.exists()  # noqa: ASYNC240 —— 确认拿到的是真实保存下来的文件
        return TranscriptResult(text=RECALL, seconds=42.5)


class InlineQueue:
    """不经过 Redis，入队时直接执行处理流程。available=False 模拟 Redis 没启动。"""

    def __init__(self, storage: LocalStorage):
        self.storage, self.available, self.enqueued = storage, True, []
        self.llm, self.transcriber = FakeLLM(), FakeTranscriber()

    async def enqueue_interview(self, interview_id):
        if not self.available:
            raise QueueUnavailable
        self.enqueued.append(interview_id)
        await process_interview(
            TestSessionLocal, lambda: self.llm, lambda: self.transcriber, self.storage, interview_id
        )


@pytest.fixture
def queue(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    q = InlineQueue(storage)
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_task_queue] = lambda: q
    yield q
    app.dependency_overrides.pop(get_storage, None)
    app.dependency_overrides.pop(get_task_queue, None)


@pytest.fixture
async def alice(user_client):
    return await user_client("alice@example.com")


async def new_app(client, company="北辰云") -> str:
    resp = await client.post("/api/applications", json={"company": company, "role": "Agent 开发"})
    return resp.json()["id"]


async def submit(
    client, app_id, *, text=None, audio: tuple[str, bytes] | None = None, round="一面"
):
    files = {"audio": (audio[0], audio[1], "application/octet-stream")} if audio else None
    data = {"round": round, **({"text": text} if text else {})}
    return await client.post(f"/api/applications/{app_id}/interviews", data=data, files=files)


# ---------- 文字输入 ----------


async def test_text_interview_is_processed_into_questions(alice, queue):
    app_id = await new_app(alice)
    resp = await submit(alice, app_id, text=RECALL)
    assert resp.status_code == 201, resp.text
    interview_id = resp.json()["id"]

    detail = (await alice.get(f"/api/interviews/{interview_id}")).json()
    assert detail["status"] == "done" and detail["error"] is None
    assert detail["company"] == "北辰云" and detail["round"] == "一面"
    assert [q["question"] for q in detail["questions"]] == [q.question for q in ANALYSIS.questions]
    assert detail["summary"]["weak_points"][0]["topic"] == "Agent 评测方法"
    assert "<recall>" in queue.llm.prompts[0] and "LRU" in queue.llm.prompts[0]
    assert queue.transcriber.calls == []  # 文字输入不需要转写

    listed = (await alice.get(f"/api/applications/{app_id}/interviews")).json()
    assert listed[0]["question_count"] == 3

    async with TestSessionLocal() as s:
        assert (await s.execute(select(func.count()).select_from(WeakPoint))).scalar_one() == 1
        [log] = (await s.execute(select(LLMCallLog))).scalars().all()
    assert log.feature == "interview_review" and log.success


# ---------- 语音输入 ----------


async def test_audio_interview_is_transcribed_then_analysed(alice, queue):
    app_id = await new_app(alice)
    resp = await submit(alice, app_id, audio=("回忆.m4a", b"fake-audio-bytes"))
    assert resp.status_code == 201, resp.text
    detail = (await alice.get(f"/api/interviews/{resp.json()['id']}")).json()
    assert detail["status"] == "done"
    assert detail["input_type"] == "audio" and detail["audio_filename"] == "回忆.m4a"
    assert detail["transcript"] == RECALL and detail["audio_seconds"] == 42.5
    assert len(queue.transcriber.calls) == 1
    assert queue.transcriber.calls[0].suffix == ".m4a"  # 存储时保留扩展名，但文件名是随机的


async def test_transcription_failure_and_retry_skips_done_steps(alice, queue):
    app_id = await new_app(alice)
    queue.transcriber.error = TranscribeError("没有识别出文字")
    interview_id = (await submit(alice, app_id, audio=("a.webm", b"x"))).json()["id"]
    failed = (await alice.get(f"/api/interviews/{interview_id}")).json()
    assert failed["status"] == "failed" and failed["error"] == "没有识别出文字"

    # 转写成功、但分析失败
    queue.transcriber.error = None
    queue.llm.error = LLMError("deepseek 请求过于频繁")
    await alice.post(f"/api/interviews/{interview_id}/retry")
    failed = (await alice.get(f"/api/interviews/{interview_id}")).json()
    assert failed["status"] == "failed" and "频繁" in failed["error"]
    assert failed["transcript"] == RECALL  # 转写结果已经保存
    assert failed["questions"] == []  # 分析失败，没有写入半截结果

    # 再次重试：已经转写过，不会再调用转写（不重复花钱）
    queue.llm.error = None
    calls_before = len(queue.transcriber.calls)
    retried = await alice.post(f"/api/interviews/{interview_id}/retry")
    assert retried.status_code == 200
    done = (await alice.get(f"/api/interviews/{interview_id}")).json()
    assert done["status"] == "done" and len(done["questions"]) == 3
    assert len(queue.transcriber.calls) == calls_before


async def test_queue_unavailable_marks_failed_then_retry_works(alice, queue):
    app_id = await new_app(alice)
    queue.available = False
    created = (await submit(alice, app_id, text=RECALL)).json()
    assert created["status"] == "failed" and "Redis" in created["error"]

    queue.available = True
    await alice.post(f"/api/interviews/{created['id']}/retry")
    assert (await alice.get(f"/api/interviews/{created['id']}")).json()["status"] == "done"


async def test_cannot_retry_finished_interview(alice, queue):
    interview_id = (await submit(alice, await new_app(alice), text=RECALL)).json()["id"]
    assert (await alice.post(f"/api/interviews/{interview_id}/retry")).status_code == 409


async def test_reprocessing_does_not_duplicate_questions(alice, queue):
    """同一个任务被重复执行（比如队列重复投递）也不能让题库出现重复题目。"""
    interview_id = (await submit(alice, await new_app(alice), text=RECALL)).json()["id"]
    async with TestSessionLocal() as s:
        from app.models import Interview, InterviewStatus

        iv = await s.get(Interview, interview_id)
        iv.status = InterviewStatus.FAILED
        await s.commit()
    await alice.post(f"/api/interviews/{interview_id}/retry")
    assert len((await alice.get("/api/questions")).json()) == 3


# ---------- 输入校验与权限 ----------


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "二选一"),
        ({"text": RECALL, "audio": ("a.mp3", b"x")}, "二选一"),
        ({"text": "太短了"}, "太短"),
        ({"audio": ("notes.docx", b"x")}, "不支持"),
        ({"text": RECALL, "round": ""}, "轮次"),
    ],
)
async def test_input_validation(alice, queue, kwargs, message):
    resp = await submit(alice, await new_app(alice), **kwargs)
    assert resp.status_code == 422
    assert message in str(resp.json()["detail"])


async def test_interviews_are_private(alice, user_client, queue):
    app_id = await new_app(alice)
    interview_id = (await submit(alice, app_id, text=RECALL)).json()["id"]
    bob = await user_client("bob@example.com")
    assert (await submit(bob, app_id, text=RECALL)).status_code == 404
    assert (await bob.get(f"/api/interviews/{interview_id}")).status_code == 404
    assert (await bob.post(f"/api/interviews/{interview_id}/retry")).status_code == 404
    assert (await bob.delete(f"/api/interviews/{interview_id}")).status_code == 404
    assert (await bob.get("/api/questions")).json() == []
    question_id = (await alice.get("/api/questions")).json()[0]["id"]
    patch = await bob.patch(f"/api/questions/{question_id}", json={"mastery": "mastered"})
    assert patch.status_code == 404


async def test_delete_removes_questions_and_audio_file(alice, queue):
    app_id = await new_app(alice)
    interview_id = (await submit(alice, app_id, audio=("a.wav", b"x"))).json()["id"]
    [audio_file] = queue.transcriber.calls
    assert audio_file.exists()
    assert (await alice.delete(f"/api/interviews/{interview_id}")).status_code == 204
    assert not audio_file.exists()
    assert (await alice.get("/api/questions")).json() == []


# ---------- 题库 ----------


async def test_question_bank_filters_and_ordering(alice, queue):
    await submit(alice, await new_app(alice, "北辰云"), text=RECALL)
    await submit(alice, await new_app(alice, "星河智能"), text=RECALL, round="二面")

    everything = (await alice.get("/api/questions")).json()
    assert len(everything) == 6
    assert everything[0]["score"] == 2  # 分数低的排前面
    assert {q["company"] for q in everything} == {"北辰云", "星河智能"}

    by_company = (await alice.get("/api/questions", params={"company": "星河智能"})).json()
    assert len(by_company) == 3 and all(q["round"] == "二面" for q in by_company)
    by_tag = (await alice.get("/api/questions", params={"tag": "缓存"})).json()
    assert len(by_tag) == 2 and all("缓存" in q["tags"] for q in by_tag)
    by_text = (await alice.get("/api/questions", params={"q": "LRU"})).json()
    assert {q["question"] for q in by_text} == {"手写 LRU 缓存"}

    target = by_tag[0]["id"]
    updated = await alice.patch(f"/api/questions/{target}", json={"mastery": "mastered"})
    assert updated.json()["mastery"] == "mastered"
    mastered = (await alice.get("/api/questions", params={"mastery": "mastered"})).json()
    assert [q["id"] for q in mastered] == [target]
    assert (await alice.get("/api/questions")).json()[-1]["id"] == target  # 已掌握的沉到最后


# ---------- 音频格式转换（真实运行 ffmpeg）----------


def _tone(path: Path, seconds: float) -> None:
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "libopus", str(path)],
        check=True,
    )  # fmt: skip


def test_webm_is_converted_to_16k_mono_wav(tmp_path):
    import wave

    src, dst = tmp_path / "rec.webm", tmp_path / "out.wav"
    _tone(src, 2.0)
    seconds = to_wav_16k(src, dst)
    assert 1.9 < seconds < 2.2
    with wave.open(str(dst), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)


def test_conversion_rejects_garbage_and_too_short(tmp_path):
    garbage = tmp_path / "bad.m4a"
    garbage.write_bytes(b"not audio at all")
    with pytest.raises(TranscribeError, match="无法识别"):
        to_wav_16k(garbage, tmp_path / "x.wav")
    short = tmp_path / "short.webm"
    _tone(short, 0.3)
    with pytest.raises(TranscribeError, match="太短"):
        to_wav_16k(short, tmp_path / "y.wav")


def test_storage_blocks_path_traversal(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.path("../../etc/passwd")
