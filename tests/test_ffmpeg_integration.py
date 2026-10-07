import subprocess

from dog_audio.media import export_clip, probe_input
from dog_audio.models import Clip


def test_real_wav_probe_and_mp3_export(tmp_path):
    source = tmp_path / "spaced ünicode.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:a", "pcm_s16le", str(source)], check=True)
    identity = probe_input(source)
    assert identity.codec == "pcm_s16le"
    assert 0.9 <= identity.duration_seconds <= 1.1
    clip = Clip(id="C001", event_ids=["E001"], start_seconds=0, end_seconds=.5,
                filename="clips/C001.mp3", part_index=1, part_count=1)
    destination = tmp_path / clip.filename
    export_clip(source, clip, destination, 128)
    assert destination.stat().st_size > 0
