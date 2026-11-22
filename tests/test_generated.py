"""Generated Actor files and copies of the shared runtime must be up to date."""

from __future__ import annotations

import subprocess
import sys
import unittest

from tests.helpers import ACTOR_SLUGS, ROOT


class GeneratedFilesTests(unittest.TestCase):
    def test_build_actors_check_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'build_actors.py'), '--check'],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_actor_has_an_endpoint_and_actor_json(self) -> None:
        self.assertEqual(len(ACTOR_SLUGS), 13)
        for slug in ACTOR_SLUGS:
            with self.subTest(slug=slug):
                self.assertTrue((ROOT / 'actors' / slug / 'my_actor' / 'endpoint.py').is_file())
                self.assertTrue((ROOT / 'actors' / slug / '.actor' / 'actor.json').is_file())


if __name__ == '__main__':
    unittest.main()
