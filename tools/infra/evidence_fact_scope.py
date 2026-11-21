"""Explicit per-fact scope inside the existing evidence review snapshot."""
from __future__ import annotations

import json
from collections import defaultdict

from tools.infra.evidence_sources import field_values

KEY = "fact_scope_v1"
_POSITION = {"field", "index", "value"}
_CLAIM = _POSITION | {"source", "attribution", "target", "environment", "implementation", "release"}
_ATTRIBUTIONS = {"self", "team_lead", "contributor", "teammate", "unknown"}



def checked_result_review(review, *, value, source_quote):
    """Validate only the server result protocol and its exact textual binding."""
    if not isinstance(value, str) or not value or not isinstance(source_quote, str) or source_quote.count(value) != 1:
        raise ValueError("result_review_ambiguous_source")
    if (not isinstance(review, dict)
            or review.keys() != {"outcome", "measurement_quote", "rationale"}
            or review["outcome"] not in ("established", "not_established", "unknown")
            or not isinstance(review["rationale"], str) or not review["rationale"].strip()):
        raise ValueError("result_review_invalid")
    quote = review["measurement_quote"]
    if quote is not None:
        if (review["outcome"] != "established" or not isinstance(quote, str) or not quote.strip()
                or value.count(quote) != 1 or source_quote.count(quote) != 1):
            raise ValueError("result_review_invalid_measurement_binding")
    return dict(review)


def _position(item, fields):
    field, index, value = (item.get(k) for k in ("field", "index", "value"))
    if field not in ("actions", "results") or type(index) is not int or not isinstance(value, str):
        raise ValueError("fact_scope_invalid_position")
    values = field_values(fields, field)
    if not 0 <= index < len(values) or values[index] != value or values.count(value) != 1:
        raise ValueError("fact_scope_invalid_position")
    return field, index, value


def _bound(item, fields, bindings, refs):
    if not isinstance(item, dict):
        raise ValueError("fact_scope_invalid")
    field, _, value = _position(item, fields)
    source = item.get("source")
    if not isinstance(source, dict) or source.keys() != {"material_id", "document_id", "sha256", "quote"}:
        raise ValueError("fact_scope_unbound")
    if (not any(all(r.get(k) == source[k] for k in ("material_id","document_id","sha256")) for r in refs)
            or not any(b.get("field") == field and b.get("value") == value
                       and all(b.get(k) == source[k] for k in ("material_id","document_id","quote")) for b in bindings)):
        raise ValueError("fact_scope_unbound")
    return item


def _unique_source(item, documents):
    source = item["source"]
    quote = source["quote"]
    text = documents.get((source["material_id"], source["document_id"]), "")
    return bool(quote) and text.find(quote) >= 0 and text.find(quote) == text.rfind(quote)


def _require_unique_sources(rows, documents):
    if any(not _unique_source(row, documents) for row in rows):
        raise ValueError("fact_scope_source_not_unique")
    return rows


def _checked(item, fields, bindings, refs):
    if not isinstance(item, dict) or item.keys() != _CLAIM:
        raise ValueError("fact_scope_invalid")
    _bound(item, fields, bindings, refs)
    target, relation = item["target"], item["attribution"]
    if (not isinstance(relation, str) or relation not in _ATTRIBUTIONS
            or not isinstance(target, str) or not target.strip() or len(target) > 160
            or target != " ".join(target.split())):
        raise ValueError("fact_scope_invalid")
    imp, release, env = (item[k] for k in ("implementation","release","environment"))
    if (imp not in ("implemented","planned","not_implemented","unknown")
            or release not in ("released","not_released","unknown")
            or env not in ("test","staging","production","unknown")
            or (relation == imp == release == "unknown")
            or (env == "unknown" and release != "unknown")
            or (release == "released" and imp in ("planned","not_implemented"))):
        raise ValueError("fact_scope_invalid")
    return item



def _checked_stored(item, fields, bindings, refs):
    if not isinstance(item, dict):
        raise ValueError("fact_scope_invalid")
    if "result_review" not in item:
        return _checked(item, fields, bindings, refs)
    _checked({key: value for key, value in item.items() if key != "result_review"}, fields, bindings, refs)
    if item["field"] != "results":
        raise ValueError("result_review_invalid")
    checked_result_review(item["result_review"], value=item["value"], source_quote=item["source"]["quote"])
    return item


def _retained(rows, fields, bindings, refs, *, validate):
    valid = []
    if not isinstance(rows, list) or len(rows) > 48:
        return valid
    for row in rows:
        try:
            checked = validate(row, fields, bindings, refs)
            if checked not in valid:
                valid.append(checked)
        except (ValueError, TypeError, AttributeError):
            continue
    return valid


def _stored_scope(scalars):
    """维护同一复审快照的既有约束，不因暂存或待复审而将其视为已撤销。"""
    try:
        snapshot = json.loads(scalars.get("reviewed_facts_json") or "{}")
    except (ValueError, TypeError) as exc:
        raise ValueError("fact_scope_invalid") from exc
    if not isinstance(snapshot, dict):
        raise ValueError("fact_scope_invalid")
    return snapshot.get(KEY, [])


def _saved(scalars):
    if scalars.get("review_decision") != "approved" or scalars.get("status") != "saved_eligible":
        return []
    try:
        return _stored_scope(scalars)
    except ValueError:
        return []


def apply_fact_scope(existing, fields, bindings, refs, directive, *, provided, documents):
    """Called only after the existing save route validates all cited source documents."""
    original = {**existing["scalars"], **existing["lists"]} if existing else {}
    saved = _stored_scope(original)
    if not isinstance(saved, list):
        raise ValueError("fact_scope_invalid")
    rows = _retained(saved, fields, bindings, refs, validate=_bound)
    if not provided:
        if any(row not in rows for row in saved):
            raise ValueError("fact_scope_unverifiable")
        return _require_unique_sources(rows, documents)
    if not isinstance(directive, dict):
        raise ValueError("fact_scope_invalid")
    kind = directive.get("kind")
    claim = {k:v for k,v in directive.items() if k != "kind"}
    position = _position(claim, original)
    if _position(claim, fields) != position:
        raise ValueError("fact_scope_invalid_position")
    def same_position(row):
        return isinstance(row, dict) and tuple(row.get(k) for k in ("field","index","value")) == position
    if any(row not in rows and not same_position(row) for row in saved):
        raise ValueError("fact_scope_unverifiable")
    if kind == "revoke" and claim.keys() == _POSITION:
        return _require_unique_sources([row for row in rows if not same_position(row)], documents)
    if kind != "adopt":
        raise ValueError("fact_scope_invalid")
    claim = _checked(claim, fields, bindings, refs)
    classified = [row for row in _retained(rows, fields, bindings, refs, validate=_checked_stored)
                  if _unique_source(row, documents)]
    rows = [row for row in rows if not (same_position(row) and (row not in classified
            or all(row[k] == claim[k] for k in ("source","target","environment"))))]
    if len(rows) >= 48:
        raise ValueError("fact_scope_limit")
    return _require_unique_sources([*rows, claim], documents)


def _checked_rows(doc, rows, refs, bindings, documents):
    fields = {**doc["scalars"], **doc["lists"]}
    bound = _retained(rows, fields, bindings, refs, validate=_bound)
    _require_unique_sources(bound, documents)
    return _retained(bound, fields, bindings, refs, validate=_checked_stored)


def _project_scopes(card_id, rows):
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = tuple(row[k] for k in ("field","index","value","target","environment"))
        grouped[key][row["attribution"]].append(row)
    out = []
    for (field,index,value,target,env), by_relation in grouped.items():
        if {"self", "teammate"}.issubset(by_relation):
            # Direct responsibility disagrees for this exact occurrence/target/environment.
            # Lead/contributor assertions are distinct and do not resolve that disagreement.
            by_relation["conflict"] = by_relation.pop("self") + by_relation.pop("teammate")
        for relation, rows in by_relation.items():
            implementations = {r["implementation"] for r in rows} - {"unknown"}
            releases = {r["release"] for r in rows} - {"unknown"}
            cross = "released" in releases and bool(implementations & {"planned","not_implemented"})
            imp_conflict = cross or ("implemented" in implementations and len(implementations) > 1)
            implementation = ("conflict" if imp_conflict else next((state for state in
                ("implemented","planned","not_implemented") if state in implementations), "unknown"))
            release = "conflict" if cross or len(releases) > 1 else next(iter(releases), "unknown")
            if relation == "conflict":
                implementation = release = "unknown"
            out.append({"fact_id":f"{card_id}:{field}:{index}", "field":field, "index":index, "value":value,
                        "attribution":relation, "target":target, "environment":env,
                        "implementation":implementation, "release":release,
                        "sources":[{**r["source"], "attribution":r["attribution"],
                                    "implementation":r["implementation"], "release":r["release"],
                                    **({"result_review": r["result_review"]} if "result_review" in r else {})} for r in rows]})
    return out


def project_fact_scope(doc, refs, bindings, *, documents):
    """Return only read-time source-revalidated, reviewed assertions to Evidence detail."""
    scalars = doc["scalars"]
    if scalars.get("candidate_pool_eligible") != "true" or not scalars.get("id"):
        return []
    return _project_scopes(scalars["id"], _checked_rows(doc, _saved(scalars), refs, bindings, documents))


def _current_scope_rows(doc, material_dir, *, card_id, validated_sources=None):
    """Read the same current source snapshot for positive and negative projections."""
    scalars = doc["scalars"]
    rows = _saved(scalars)
    if not rows:
        return [], []
    if scalars.get("id") != card_id:
        raise ValueError("fact_scope_card_identity_mismatch")
    from tools.infra.evidence_sources import assert_source_snapshot, validated_source_inputs

    sources = validated_source_inputs(doc, material_dir) if validated_sources is None else validated_sources
    if not sources:
        raise ValueError("fact_scope_source_unverified")
    assert_source_snapshot(sources.snapshots)
    refs = json.loads(scalars.get("source_documents_json") or "[]")
    bindings = json.loads(scalars.get("field_sources_json") or "[]")
    bound = _retained(rows, {**scalars, **doc["lists"]}, bindings, refs, validate=_bound)
    if not isinstance(rows, list) or any(row not in bound for row in rows):
        raise ValueError("fact_scope_unverifiable")
    _require_unique_sources(bound, sources.documents)
    return bound, _retained(bound, {**scalars, **doc["lists"]}, bindings, refs, validate=_checked_stored)


def _result_reviews(card_id, bound, checked):
    """Select a complete supporting row; never combine verdicts or count source votes."""
    out = {}
    for row in checked:
        if (row["field"] != "results" or row["attribution"] not in {"self", "team_lead", "contributor"}
                or row.get("result_review", {}).get("outcome") != "established"):
            continue
        occurrence = (row["field"], row["index"], row["value"])
        peers = [peer for peer in bound
                 if tuple(peer[key] for key in ("field", "index", "value")) == occurrence]
        # Unclassified stored constraints cannot be silently discarded to obtain a positive.
        if any(peer not in checked for peer in peers):
            continue
        related = [peer for peer in peers
                   if (peer["target"], peer["environment"]) == (row["target"], row["environment"])]
        projected = _project_scopes(card_id, related)
        implementations = {peer["implementation"] for peer in related} - {"unknown"}
        releases = {peer["release"] for peer in related} - {"unknown"}
        conflict = (any(peer["attribution"] == "conflict" for peer in projected)
                    or ("implemented" in implementations and len(implementations) > 1)
                    or len(releases) > 1
                    or ("released" in releases and bool(implementations & {"planned", "not_implemented"}))
                    or any(peer.get("result_review", {}).get("outcome") == "not_established" for peer in related))
        if conflict:
            continue
        fid = f'{card_id}:results:{row["index"]}'
        # A missing or different measured proposition is not contrary evidence. Prefer
        # an entire supporting measured row without taking any field from another row.
        if fid not in out or (out[fid]["result_review"]["measurement_quote"] is None
                              and row["result_review"]["measurement_quote"] is not None):
            out[fid] = row
    return out


def current_result_reviews(doc, material_dir, *, card_id, validated_sources=None):
    """Current, source-bound complete results shared by both renderers and quality."""
    if doc["scalars"].get("candidate_pool_eligible") != "true":
        return {}
    bound, checked = _current_scope_rows(doc, material_dir, card_id=card_id,
                                        validated_sources=validated_sources)
    return _result_reviews(card_id, bound, checked)


def personal_claim_exclusions(doc, material_dir, *, card_id, validated_sources=None):
    """Keep action scope closed; only independently established complete results open."""
    bound, checked = _current_scope_rows(doc, material_dir, card_id=card_id,
                                        validated_sources=validated_sources)
    allowed = (_result_reviews(card_id, bound, checked)
               if doc["scalars"].get("candidate_pool_eligible") == "true" else {})
    return frozenset(f'{card_id}:{row["field"]}:{row["index"]}' for row in bound).difference(allowed)


def nonpersonal_reviewed_fact_ids(doc, material_dir, *, card_id, validated_sources):
    """Current, source-bound negative attribution only; ambiguous scopes do not prove it."""
    if doc["scalars"].get("candidate_pool_eligible") != "true":
        return frozenset()
    bound, checked = _current_scope_rows(doc, material_dir, card_id=card_id,
                                        validated_sources=validated_sources)
    unknown = {f'{card_id}:{row["field"]}:{row["index"]}' for row in bound if row not in checked}
    grouped = defaultdict(set)
    for row in _project_scopes(card_id, checked):
        grouped[row["fact_id"]].add(row["attribution"])
    return frozenset(fid for fid, relations in grouped.items()
                     if fid not in unknown and relations <= {"teammate", "conflict"})
