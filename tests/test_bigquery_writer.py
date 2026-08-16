from unittest.mock import MagicMock

import pytest

from ingestion.binance.bigquery_writer import BigQueryTickWriter


def make_writer(flush_every=3):
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = None  # success: .result() doesn't raise
    mock_client.load_table_from_json.return_value = mock_job
    writer = BigQueryTickWriter(
        table_name="depth_ticks",
        symbol="BTCUSDT",
        project_id="test-project",
        dataset="test_dataset",
        flush_every=flush_every,
        client=mock_client,
    )
    return writer, mock_client, mock_job


def test_ensures_table_exists_on_construction():
    writer, mock_client, _ = make_writer()
    mock_client.create_table.assert_called_once()
    call_kwargs = mock_client.create_table.call_args
    assert call_kwargs.kwargs.get("exists_ok") is True


def test_table_ref_uses_raw_prefix_convention():
    writer, _, _ = make_writer()
    assert writer.table_ref == "test-project.test_dataset.raw_depth_ticks"


def test_auto_flush_triggers_load_job_at_threshold():
    writer, mock_client, mock_job = make_writer(flush_every=3)

    for i in range(3):
        writer.add({"ts_ms": i, "best_bid": 100.0, "best_ask": 100.5})

    assert len(writer) == 0  # buffer cleared after auto-flush
    mock_client.load_table_from_json.assert_called_once()
    loaded_rows = mock_client.load_table_from_json.call_args[0][0]
    assert len(loaded_rows) == 3
    mock_job.result.assert_called_once()  # waited for the job to actually finish


def test_flush_raises_on_load_job_failure_and_preserves_buffer_for_retry():
    writer, mock_client, mock_job = make_writer(flush_every=100)
    mock_job.result.side_effect = RuntimeError("load job failed")

    writer.add({"ts_ms": 1})

    with pytest.raises(RuntimeError, match="load job failed"):
        writer.flush()

    assert len(writer) == 1  # failed rows were NOT dropped - still there to retry


def test_flush_is_a_noop_on_empty_buffer():
    writer, mock_client, _ = make_writer()
    writer.flush()
    mock_client.load_table_from_json.assert_not_called()
