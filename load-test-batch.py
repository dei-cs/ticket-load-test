import asyncio
import random
import time
import aiohttp
from collections import Counter

ENDPOINT = "http://localhost:8003/cart/reserve-batch"
CONCURRENCY = 1000
OWNER = "load-test-bot"


async def reserve(session: aiohttp.ClientSession, i: int) -> dict:
    count = random.randint(1, 5)
    try:
        async with session.post(ENDPOINT, params={"count": count, "owner": f"{OWNER}-{i}"}) as resp:
            body = await resp.json()
            return {"status": resp.status, "count": count, "body": body}
    except Exception as e:
        return {"status": "error", "count": count, "body": str(e)}


async def main():
    start = time.perf_counter()

    async with aiohttp.ClientSession() as session:
        tasks = [reserve(session, i) for i in range(CONCURRENCY)]
        results = await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - start
    status_counts = Counter(r["status"] for r in results)
    total_reserved = sum(
        len(r["body"].get("reserved", [])) for r in results if r["status"] == 200
    )

    print(f"\n=== Results ({CONCURRENCY} concurrent requests) ===")
    for status, count in sorted(status_counts.items(), key=lambda x: str(x[0])):
        print(f"  HTTP {status}: {count} requests")
    print(f"  Total tickets reserved: {total_reserved}")
    print(f"  Elapsed: {elapsed:.2f}s")

    errors = [r for r in results if r["status"] == "error"]
    if errors:
        print(f"\n  Errors:")
        for e in errors[:5]:
            print(f"    {e['body']}")


if __name__ == "__main__":
    asyncio.run(main())
