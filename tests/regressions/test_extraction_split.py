"""The API rejected the single ExtractionRecord schema ("compiled grammar is too large").

The extraction is now requested as two parts and merged in code. These tests keep the merged
record out of the request path and keep the merge lossless.
"""
import asyncio

from src.chain import Chain, load_context
from src.llm import LLMClient
from src.schemas import ExtractionPartA, ExtractionPartB, ExtractionRecord
from tests.fakes import FakeBackend, extraction_a, scripted_clean_run


def test_parts_cover_the_record_exactly():
    a, b = set(ExtractionPartA.model_fields), set(ExtractionPartB.model_fields)
    assert not a & b
    assert a | b == set(ExtractionRecord.model_fields)


def test_merge_is_lossless():
    rec = extraction_a()
    assert ExtractionRecord.from_parts(rec.part_a(), rec.part_b()) == rec


def test_chain_never_requests_the_merged_schema(tmp_path):
    fb = scripted_clean_run(FakeBackend())
    llm = LLMClient(mode="live", backend=fb, db_path=tmp_path / "t.sqlite3", replay_dir=tmp_path / "rp",
                    redact=lambda s: s)
    result = asyncio.run(Chain(llm).run(load_context("deal_a")))
    names = [n for n, _ in fb.requests]
    assert "ExtractionRecord" not in names
    assert names[:2] == ["ExtractionPartA", "ExtractionPartB"]
    assert result.extraction == extraction_a()
