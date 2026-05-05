# enrichers/entity_extraction.py
"""
Entity Extraction Enricher — LLM 抽取通用实体。

触发条件：body_text 长度 > 200 字

产出：
  - organizations / products / technologies / people
  - 每个实体作为 subject 候选（confidence=0.7）

enrichment_level = 3 (L3)
"""

from __future__ import annotations

import json
import re
import time

from enrichers.base import BaseEnricher, EnrichmentResult, SubjectCandidate
from enrichers.registry import register
from infra.llm import call_llm


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '-', s)
    return s.strip('-')


@register("entity_extraction")
class EntityExtractionEnricher(BaseEnricher):
    enrichment_type = "entity_extraction"

    def applies_to(self, item: dict) -> bool:
        body = item.get("body_text") or ""
        return len(body) > 200

    def run(self, item: dict) -> EnrichmentResult | None:
        prompt_cfg = self.config.get_prompt("enrich_entity_extraction")
        if not prompt_cfg or not self.api_key:
            return None

        body = item.get("body_text") or ""
        title = item.get("processed_title") or item.get("raw_title") or ""
        summary = item.get("summary") or ""

        prompt = prompt_cfg.render(
            title=title,
            summary=summary[:300],
            body_text=body[:2000],
        )

        ai = call_llm(prompt, prompt_cfg, system_prompt="You only output JSON.", api_key=self.api_key)
        if not ai:
            return None

        subject_candidates: list[SubjectCandidate] = []
        seen_slugs: set[str] = set()

        for entity_type, role in [
            ("organizations", "mentioned_org"),
            ("products", "mentioned_product"),
            ("technologies", "mentioned_tech"),
            ("people", "mentioned_person"),
        ]:
            entities = ai.get(entity_type) or []
            for ent in entities:
                if not isinstance(ent, dict):
                    continue
                name = ent.get("name") or ""
                if not name:
                    continue
                slug = ent.get("slug") or _slugify(name)
                if not slug or slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                subject_candidates.append(SubjectCandidate(
                    slug=slug,
                    type=entity_type.rstrip("s"),  # organizations → organization
                    display_name=name,
                    description=(ent.get("description") or "")[:200],
                    metadata={"entity_type": entity_type},
                    role=role,
                    context=f"从正文抽取: {title[:50]}",
                    confidence=0.7,
                ))

        time.sleep(prompt_cfg.request_interval)

        return EnrichmentResult(
            enrichment_type=self.enrichment_type,
            enricher_name=self.name,
            data={
                "entities": {
                    "organizations": ai.get("organizations") or [],
                    "products": ai.get("products") or [],
                    "technologies": ai.get("technologies") or [],
                    "people": ai.get("people") or [],
                },
                "entity_count": len(subject_candidates),
            },
            subject_candidates=subject_candidates,
        )
