# Bu betik, worker isleyisini tek seferlik yerel denemeler icin calistirir.

import asyncio
import json

from worker.jobs import sample_health_job


async def main() -> None:
    result = await sample_health_job({}, {"source": "local_smoke"})
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    asyncio.run(main())

