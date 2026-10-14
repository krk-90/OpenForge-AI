import asyncio

import pytest

from APP.core.resilience import invoke_with_retry, retry_async
from Evalution.metrics import evaluate_retrieval, percentile, recall_at_k, reciprocal_rank


class TemporaryProviderError(Exception):
    status_code = 503


def test_retry_async_retries_transient_provider_error():
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TemporaryProviderError("temporarily unavailable")
        return "ok"

    assert asyncio.run(retry_async(operation, attempts=3, base_delay=0)) == "ok"
    assert calls == 3


def test_retry_async_does_not_retry_permanent_error():
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        raise ValueError("invalid request")

    with pytest.raises(ValueError):
        asyncio.run(retry_async(operation, attempts=4, base_delay=0))
    assert calls == 1


def test_invoke_with_retry_records_usage_without_changing_result():
    class Result:
        content = "answer"
        usage_metadata = {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}

    class FakeLLM:
        async def ainvoke(self, input_data):
            assert input_data == "question"
            return Result()

    result = asyncio.run(invoke_with_retry(FakeLLM(), "question", operation="unit_test"))
    assert result.content == "answer"


def test_retrieval_metrics_use_labelled_ground_truth():
    cases = [
        {"id": "a", "retrieved_ids": ["x", "gold"], "relevant_ids": ["gold"]},
        {"id": "b", "retrieved_ids": ["miss"], "relevant_ids": ["gold"]},
    ]
    result = evaluate_retrieval(cases, k=5)
    assert result["case_count"] == 2
    assert result["recall_at_k"] == 0.5
    assert result["mrr"] == 0.25
    assert recall_at_k(["gold"], ["gold"], 1) == 1.0
    assert reciprocal_rank(["miss", "gold"], ["gold"]) == 0.5


def test_metrics_reject_missing_ground_truth_and_empty_latency():
    with pytest.raises(ValueError):
        recall_at_k(["a"], [], 5)
    with pytest.raises(ValueError):
        percentile([], 95)


def test_nearest_rank_percentile():
    assert percentile([10, 20, 30, 40], 50) == 20
    assert percentile([10, 20, 30, 40], 95) == 40


def test_online_evaluator_validates_response_contract():
    from Evalution.online import evaluate_response

    case = {
        "name": "sample",
        "path": "/sample",
        "checks": {
            "required_fields": ["answer"],
            "non_empty_fields": ["answer"],
        },
    }
    assert evaluate_response(case, 200, {"answer": "grounded response"})["status"] == "passed"
    result = evaluate_response(case, 200, {"answer": ""})
    assert result["status"] == "failed"
    assert "Empty field: answer" in result["checks"]
