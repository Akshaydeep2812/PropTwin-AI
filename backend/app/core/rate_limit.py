from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

# In-process counters are per worker process; run one worker or add shared storage when scaling out.
limiter = Limiter(key_func=get_remote_address, enabled=get_settings().rate_limit_enabled)
