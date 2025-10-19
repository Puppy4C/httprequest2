#!/usr/bin/env python3
"""
命令行压测器

用法示例:
  python3 cli_runner.py --target http://107.174.71.236/api/search --concurrency 10 --duration 120

输出示例: 打印请求数、成功、失败、平均响应时间、运行时间、最后一次响应。
"""
import argparse
import asyncio
import time
import sys
import random
from faker import Faker
import httpx


def parse_args():
    p = argparse.ArgumentParser(description='简单命令行压测器')
    p.add_argument('--target', required=True, help='目标 URL, 例如 http://host/api/search')
    p.add_argument('--concurrency', '-c', type=int, default=10)
    p.add_argument('--duration', '-d', type=int, default=10, help='持续时间(秒)')
    p.add_argument('--rps', type=float, default=0, help='最大每秒请求数 (0 表示不限制)')
    return p.parse_args()


class Runner:
    def __init__(self, target, concurrency, duration):
        self.target = target
        self.concurrency = concurrency
        self.duration = duration
        self.rps = 0.0
        # token bucket
        self._tokens = 0.0
        self._last_fill = time.time()
        self.fake = Faker(locale='zh_CN')
        self.total = 0
        self.success = 0
        self.failure = 0
        self.total_time = 0.0
        self.last_response = None

    async def _one(self, client: httpx.AsyncClient):
        # rate limit: token bucket shared
        if self.rps and self.rps > 0:
            # refill tokens based on elapsed time
            now = time.time()
            elapsed = now - self._last_fill
            self._tokens += elapsed * self.rps
            # cap burst to 2s worth
            if self._tokens > self.rps * 2:
                self._tokens = self.rps * 2
            self._last_fill = now

            # If not enough tokens for one request, compute exact wait time
            # This allows fractional rps < 1 (e.g. 0.5 rps -> one request every 2 seconds)
            while self._tokens < 1.0:
                # tokens needed
                needed = 1.0 - self._tokens
                # time to wait (seconds) until enough tokens are available
                # rps > 0 here so division is safe
                wait = needed / self.rps
                # avoid spinning too finely, but allow precise waits for low rps
                await asyncio.sleep(max(0.01, wait))
                now = time.time()
                elapsed = now - self._last_fill
                self._tokens += elapsed * self.rps
                self._last_fill = now
            # consume a token
            self._tokens -= 1.0
            name = self.fake.name()
            # add loadMore param with random int between 1 and 5
            params = {'q': name, 'loadMore': random.randint(1, 5)}
            start = time.time()
            try:
                resp = await client.get(self.target, params=params, timeout=10.0)
                elapsed = time.time() - start
                self.total += 1
                self.total_time += elapsed
                if 200 <= resp.status_code < 300:
                    self.success += 1
                else:
                    self.failure += 1
                try:
                    body = resp.text
                except Exception:
                    body = repr(resp.content)
                self.last_response = (resp.status_code, body[:2000])
            except Exception as e:
                self.total += 1
                self.failure += 1
                self.last_response = (None, f'exception: {e}')

    async def worker(self, client: httpx.AsyncClient, end_time: float):
        while time.time() < end_time:
            await self._one(client)
            await asyncio.sleep(0)

    async def run(self):
        end_time = time.time() + self.duration
        # set up rps tokens values
        self._tokens = 0.0
        self._last_fill = time.time()
        async with httpx.AsyncClient() as client:
            tasks = [asyncio.create_task(self.worker(client, end_time)) for _ in range(self.concurrency)]

            # reporter task for dynamic output
            async def reporter():
                try:
                    while time.time() < end_time:
                        avg = (self.total_time / self.total) if self.total > 0 else 0
                        last_status = self.last_response[0] if self.last_response else '-'
                        last_body = ''
                        if self.last_response and self.last_response[1]:
                            # single-line snippet, truncate
                            last_body = str(self.last_response[1]).replace('\n', ' ')[:120]
                        msg = (f"elapsed={int(time.time() - (end_time - self.duration))}s | total={self.total} | "
                               f"success={self.success} | failure={self.failure} | avg={avg:.3f}s | last={last_status} | {last_body}")
                        # clear line and print
                        sys.stdout.write('\r' + msg)
                        sys.stdout.flush()
                        await asyncio.sleep(1)
                except asyncio.CancelledError:
                    return

            rep = asyncio.create_task(reporter())

            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                for t in tasks:
                    if not t.done():
                        t.cancel()
            finally:
                # stop reporter and move to next line
                rep.cancel()
                try:
                    await rep
                except Exception:
                    pass
                sys.stdout.write('\n')
                sys.stdout.flush()

    def report(self, start_time, end_time):
        elapsed = end_time - start_time
        avg = None
        if self.total > 0:
            avg = self.total_time / self.total
        print('--- result ---')
        print(f'total requests: {self.total}')
        print(f'success: {self.success}')
        print(f'failure: {self.failure}')
        print(f'average response time: {avg:.3f}s' if avg is not None else 'average response time: -')
        print(f'run time: {elapsed:.3f}s')
        if self.last_response:
            code, body = self.last_response
            body_snip = str(body).replace('\n', ' ')[:1000]
            print(f'last response status: {code}')
            print('last response body snippet:')
            print(body_snip)
        else:
            print('last response: -')


def main():
    args = parse_args()
    r = Runner(args.target, args.concurrency, args.duration)
    r.rps = float(args.rps)
    start = time.time()
    try:
        asyncio.run(r.run())
    except KeyboardInterrupt:
        print('\ninterrupted')
    end = time.time()
    r.report(start, end)


if __name__ == '__main__':
    main()
