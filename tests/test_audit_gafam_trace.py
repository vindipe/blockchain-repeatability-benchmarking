import tempfile
import unittest
from pathlib import Path

from analysis.audit_gafam_trace import (
    DEFAULT_INPUT,
    DEFAULT_TRACE,
    EXPECTED_TRACE_SHA256,
    parse_trace,
    run,
    sha256_file,
    validate_trace,
)


class GafamTraceAuditTests(unittest.TestCase):
    def test_trace_checksum_and_schedule(self):
        self.assertEqual(sha256_file(DEFAULT_TRACE), EXPECTED_TRACE_SHA256)
        identifier, contract, schedule = parse_trace(DEFAULT_TRACE)
        validate_trace(identifier, contract, schedule)
        self.assertEqual(schedule[0], 19_800)
        self.assertEqual(schedule[1], 115)
        self.assertEqual(schedule[300], 0)

    def test_run_writes_auditable_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = run(DEFAULT_INPUT, DEFAULT_TRACE, Path(directory))
            self.assertEqual(summary["trace_duration_seconds"], 300)
            self.assertEqual(summary["corpus_link"]["selected_observations"], 668)
            self.assertTrue((Path(directory) / "gafam_trace_audit.json").is_file())
            self.assertTrue((Path(directory) / "gafam_trace_schedule.csv").is_file())


if __name__ == "__main__":
    unittest.main()
