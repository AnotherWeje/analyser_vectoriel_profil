import redis
import os

r = redis.Redis.from_url(str(os.getenv("REDIS_URLL")))

r.set('foo', 'bar') # type: ignore
value = r.get('foo') # type: ignore