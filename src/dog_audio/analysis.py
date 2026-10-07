from .models import Clip, Event, Frame, Metrics
from .util import format_elapsed


def interval_union(intervals: list[tuple[float, float]]) -> float:
    valid = sorted((start, end) for start, end in intervals if end > start)
    if not valid:
        return 0.0
    total = 0.0
    left, right = valid[0]
    for start, end in valid[1:]:
        if start <= right:
            right = max(right, end)
        else:
            total += right - left
            left, right = start, end
    return total + right - left


def assemble_events(frames: list[Frame], onset: float, offset: float, merge_gap: float) -> list[Event]:
    groups: list[list[Frame]] = []
    current: list[Frame] = []
    for frame in sorted(frames, key=lambda item: item.start_seconds):
        if not current:
            if frame.score >= onset:
                current = [frame]
        elif frame.score >= offset:
            current.append(frame)
        else:
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    merged: list[list[Frame]] = []
    for group in groups:
        if merged and group[0].start_seconds - merged[-1][-1].end_seconds <= merge_gap:
            merged[-1].extend(group)
        else:
            merged.append(group)
    events = []
    for number, group in enumerate(merged, 1):
        start, end = group[0].start_seconds, group[-1].end_seconds
        scores = [frame.score for frame in group]
        events.append(Event(id=f"E{number:03d}", start_seconds=start, end_seconds=end,
                            start_elapsed=format_elapsed(start), end_elapsed=format_elapsed(end),
                            span_seconds=end-start, peak_score=max(scores), mean_score=sum(scores)/len(scores)))
    return events


def build_clips(events: list[Event], duration: float, padding: float, max_seconds: float) -> list[Clip]:
    regions: list[tuple[float, float, list[str]]] = []
    for event in events:
        start, end = max(0, event.start_seconds-padding), min(duration, event.end_seconds+padding)
        if regions and start <= regions[-1][1]:
            old_start, old_end, ids = regions[-1]
            regions[-1] = (old_start, max(old_end, end), ids + [event.id])
        else:
            regions.append((start, end, [event.id]))
    clips: list[Clip] = []
    for start, end, ids in regions:
        part_count = max(1, int((end-start + max_seconds - 1e-12) // max_seconds))
        for part in range(part_count):
            clip_start, clip_end = start + part*max_seconds, min(end, start+(part+1)*max_seconds)
            clip_id = f"C{len(clips)+1:03d}"
            clips.append(Clip(id=clip_id, event_ids=ids, start_seconds=clip_start, end_seconds=clip_end,
                              filename=f"clips/{clip_id}_part-{part+1:02d}-of-{part_count:02d}.mp3",
                              part_index=part+1, part_count=part_count))
            for event in events:
                if event.id in ids:
                    event.clip_ids.append(clip_id)
    return clips


def calculate_metrics(events: list[Event], clips: list[Clip], duration: float,
                      analyzed_intervals: list[tuple[float, float]], complete: bool) -> Metrics:
    analyzed = interval_union(analyzed_intervals)
    spans = [event.span_seconds for event in events]
    return Metrics(analyzed_seconds=analyzed,
                   coverage_percent=(analyzed/duration*100 if complete and duration else None),
                   active_seconds=interval_union([(event.start_seconds, event.end_seconds) for event in events]),
                   episode_span_seconds=sum(spans),
                   review_seconds=interval_union([(clip.start_seconds, clip.end_seconds) for clip in clips]),
                   first_detection_seconds=(events[0].start_seconds if events else None),
                   longest_episode_seconds=(max(spans) if spans else None), episode_count=len(events))

