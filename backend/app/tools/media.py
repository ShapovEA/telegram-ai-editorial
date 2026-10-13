import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.db.models import MediaFile
from app.db.session import session_scope
from app.tools import sandbox

log = logging.getLogger(__name__)

CHART_CODE = """
import json
import matplotlib.pyplot as plt
spec = json.loads(open('chart.json', encoding='utf-8').read())
fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
labels, values = spec['labels'], spec['values']
color = '#2f6fdf'
if spec.get('kind') == 'line':
    ax.plot(labels, values, marker='o', linewidth=2.5, color=color)
else:
    bars = ax.bar(labels, values, color=color, width=0.6)
    for b, v in zip(bars, values):
        ax.annotate(f"{v:g}", (b.get_x() + b.get_width() / 2, b.get_height()), ha='center', va='bottom', fontsize=10, xytext=(0, 3), textcoords='offset points')
ax.set_title(spec['title'], fontsize=13, loc='left', pad=12)
if spec.get('unit'):
    ax.set_ylabel(spec['unit'])
for side in ('top', 'right'):
    ax.spines[side].set_visible(False)
ax.grid(axis='y', alpha=0.25)
plt.xticks(rotation=0 if max(len(str(x)) for x in labels) < 8 else 20, ha='right' if max(len(str(x)) for x in labels) >= 8 else 'center')
fig.tight_layout()
fig.savefig('chart.png')
print('ok')
"""


async def chart(channel_id: int, spec: dict[str, Any]) -> dict[str, Any] | None:
    if len(spec.get("labels") or []) != len(spec.get("values") or []) or len(spec.get("values") or []) < 2:
        return None
    try:
        result = await sandbox.run_python(CHART_CODE, files={"chart.json": json.dumps(spec, ensure_ascii=False)}, timeout=30)
    except sandbox.SandboxError as exc:
        log.warning("chart failed: %s", exc)
        return None
    if not result.ok or not result.images:
        return None
    async with session_scope() as s:
        mf = MediaFile(channel_id=channel_id, content_type="image/png", data=result.images[0], meta={"kind": "chart", "spec": spec})
        s.add(mf)
        await s.flush()
        media_id = mf.id
    return {"kind": "chart", "media_id": media_id}


async def stock_photo(query: str) -> dict[str, Any] | None:
    key = get_settings().pexels_api_key
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": 3, "orientation": "landscape"},
                headers={"Authorization": key},
            )
            resp.raise_for_status()
            photos = resp.json().get("photos") or []
    except Exception as exc:
        log.warning("pexels failed: %s", exc)
        return None
    if not photos:
        return None
    p = photos[0]
    return {"kind": "stock", "url": p["src"].get("large") or p["src"]["original"], "credit": p.get("photographer", ""), "page": p.get("url"), "query": query}
