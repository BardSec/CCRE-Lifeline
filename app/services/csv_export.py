from __future__ import annotations

import csv
import io

from sqlalchemy.orm import Session, joinedload

from app.models import Evaluation, RubricDomain, RubricItem, Score


def _text(value: str | None) -> str:
    """Free text from users; prefix formula-like cells so Excel shows them as text."""
    value = value or ""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def generate_evaluation_csv(db: Session, eval_obj: Evaluation) -> io.StringIO:
    scores = (
        db.query(Score)
        .join(RubricItem)
        .join(RubricDomain)
        .filter(Score.evaluation_id == eval_obj.id)
        .options(joinedload(Score.rubric_item).joinedload(RubricItem.domain))
        .order_by(RubricDomain.sort_order, RubricItem.sort_order)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "evaluation_title",
        "period_start",
        "period_end",
        "status",
        "domain",
        "item_code",
        "item_title",
        "maturity_level",
        "confidence",
        "rationale",
        "compensating_controls",
        "updated_at",
    ])

    for s in scores:
        item = s.rubric_item
        writer.writerow([
            _text(eval_obj.title),
            eval_obj.period_start.date(),
            eval_obj.period_end.date(),
            eval_obj.status.value,
            item.domain.name,
            item.code,
            item.title,
            s.maturity_level if s.maturity_level > 0 else "",
            s.confidence.value if s.confidence else "",
            _text(s.rationale),
            _text(s.compensating_controls),
            s.updated_at.isoformat() if s.updated_at else "",
        ])

    output.seek(0)
    return output
