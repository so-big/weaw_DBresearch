"""Background worker. The jobs-table loop (OCR, purge) arrives in Phase 2."""

import logging
import time

log = logging.getLogger("dbresearch.worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.info("worker started; job loop not implemented yet (Phase 2)")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
