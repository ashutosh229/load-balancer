import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx


async def worker(client, url, results, duration):
    end = time.time() + duration

    while time.time() < end:
        start = time.perf_counter()

        try:
            response = await client.get(url)

            latency = (time.perf_counter() - start) * 1000

            # Treat only 2xx and 3xx responses as successful.
            success = 200 <= response.status_code < 400

            results.append(
                {
                    "ok": success,
                    "latency": latency,
                    "status": response.status_code,
                }
            )

        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000

            results.append(
                {
                    "ok": False,
                    "latency": latency,
                    "error": str(exc),
                }
            )


async def run_load(target: str, concurrency: int, duration: int = 30):
    results = []

    timeout = httpx.Timeout(10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [
            asyncio.create_task(worker(client, target, results, duration))
            for _ in range(concurrency)
        ]

        await asyncio.gather(*tasks)

    total = len(results)
    successful = sum(1 for result in results if result["ok"])
    failed = total - successful

    latencies = [result["latency"] for result in results if result["ok"]]

    summary = {
        "target": target,
        "concurrency": concurrency,
        "duration": duration,
        "total_requests": total,
        "successful": successful,
        "failed": failed,
        "error_rate": failed / total if total else 0,
        "rps": total / duration if duration else 0,
        "latency_avg_ms": (statistics.mean(latencies) if latencies else None),
        "latency_p50_ms": (statistics.median(latencies) if latencies else None),
        "latency_p95_ms": (
            statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else None
        ),
        "latency_p99_ms": (
            statistics.quantiles(latencies, n=100)[98]
            if len(latencies) >= 100
            else None
        ),
    }

    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="HTTP load generator")

    parser.add_argument(
        "--target",
        required=True,
        help="Target URL to send requests to",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of concurrent workers",
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Duration of the test in seconds",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Path to output JSON file",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.concurrency <= 0:
        raise ValueError("Concurrency must be greater than 0")

    if args.duration <= 0:
        raise ValueError("Duration must be greater than 0")

    print("Starting load test...")
    print(f"Target      : {args.target}")
    print(f"Concurrency : {args.concurrency}")
    print(f"Duration    : {args.duration}s")
    print()

    summary = asyncio.run(
        run_load(
            target=args.target,
            concurrency=args.concurrency,
            duration=args.duration,
        )
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)

    print("Load test completed.")
    print()
    print(f"Total requests : {summary['total_requests']}")
    print(f"Successful     : {summary['successful']}")
    print(f"Failed         : {summary['failed']}")
    print(f"Error rate     : {summary['error_rate']:.2%}")
    print(f"RPS            : {summary['rps']:.2f}")

    if summary["latency_avg_ms"] is not None:
        print(f"Average latency: {summary['latency_avg_ms']:.2f} ms")
        print(f"P50 latency    : {summary['latency_p50_ms']:.2f} ms")

    if summary["latency_p95_ms"] is not None:
        print(f"P95 latency    : {summary['latency_p95_ms']:.2f} ms")

    if summary["latency_p99_ms"] is not None:
        print(f"P99 latency    : {summary['latency_p99_ms']:.2f} ms")

    print()
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
