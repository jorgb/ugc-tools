"""
Decodes SP404mk2 .SMP sample files into standard PCM WAV files.
See convert/xpj/DESIGN.md section 6 and testing/SP404mk2/SMPL.txt.
"""

import array
import wave

HEADER_SIZE = 0x200


def write_wav(sample_info, smp_path, wav_path):
    """Decodes one .SMP file's PCM payload into a standard little-endian WAV.

    `sample_info` is an already-parsed sp404.smp.Sample for smp_path, so the
    header doesn't need to be re-read here.
    """
    frame_count = sample_info.size * sample_info.mode.value

    with open(smp_path, 'rb') as f:
        f.seek(HEADER_SIZE)
        payload = f.read(frame_count * 2)

    # payload is 16-bit big-endian PCM; byteswap() flips it to the native
    # byte order, which is little-endian on every platform this runs on
    samples = array.array('h')
    samples.frombytes(payload)
    samples.byteswap()

    with wave.open(wav_path, 'wb') as w:
        w.setnchannels(sample_info.mode.value)
        w.setsampwidth(2)
        w.setframerate(sample_info.samplerate)
        w.writeframes(samples.tobytes())
