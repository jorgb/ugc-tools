import sys
import struct
import os

# Define the width for the hex dump (32 bytes as requested)
HEX_DUMP_WIDTH = 32

def hex_dump(data, label="Data Dump"):
    """
    Prints a block of bytes in a standard hexadecimal dump format.
    32 hex values on the left, colon, then printable characters on the right.
    """
    if not data:
        print(f"  [{label}] (Empty Data)")
        return

    print(f"\n  [Hex Dump for {label}]")
    print(f"  Offset | {' '.join([f'{i:02X}' for i in range(HEX_DUMP_WIDTH)])} | Text")
    print("-" * (18 + 3 * HEX_DUMP_WIDTH + 10))

    for i in range(0, len(data), HEX_DUMP_WIDTH):
        line = data[i:i + HEX_DUMP_WIDTH]
        
        # Hex part: Format bytes as two-digit hex strings
        hex_values = ' '.join(f'{b:02X}' for b in line)
        
        # ASCII part: Replace non-printable ASCII characters (below 32 or above 126) with a dot
        ascii_chars = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in line)
        
        # Print the line, ensuring the hex part is padded correctly for the last line
        print(f"  {i:06X} | {hex_values:<{HEX_DUMP_WIDTH * 3 - 1}} | {ascii_chars}")
    print("-" * (18 + 3 * HEX_DUMP_WIDTH + 10))

def parse_wav_file(filepath):
    """
    Manually walks through the RIFF blocks of a WAV file, parses core data
    from 'fmt ', and dumps any other blocks (like 'LIST') as hexadecimal data.
    """
    print(f"--- Parsing RIFF WAV File Structure: {filepath} ---")

    if not os.path.exists(filepath):
        print(f"Error: File not found at '{filepath}'")
        return

    try:
        with open(filepath, 'rb') as f:
            # 1. Read Main RIFF Header (12 bytes)
            # Format: < 4s I 4s : ChunkID (RIFF), ChunkSize (File Length - 8), Format (WAVE)
            header = f.read(12)
            if len(header) < 12:
                raise ValueError("File too small to be a valid RIFF file.")
                
            chunk_id, chunk_size, riff_format = struct.unpack('<4sI4s', header)
            
            chunk_id = chunk_id.decode('ascii', 'ignore')
            riff_format = riff_format.decode('ascii', 'ignore')

            if chunk_id != 'RIFF' or riff_format != 'WAVE':
                raise ValueError(f"Invalid RIFF header: expected 'RIFF'/'WAVE', got '{chunk_id}'/'{riff_format}'")
            
            print(f"-> RIFF Header Found (Size: {chunk_size} bytes)")
            
            # Keep track of file end position for bounds checking
            file_end_pos = chunk_size + 8 # RIFF size + 8 bytes for ChunkID and ChunkSize
            
            # 2. Iterate through Sub-Chunks
            while f.tell() < file_end_pos:
                pos = f.tell()
                
                chunk_header = f.read(8)
                if len(chunk_header) == 0:
                    break
                if len(chunk_header) < 8:
                    print(f"\nWarning: Incomplete chunk header read at offset {f.tell()-len(chunk_header)}. Stopping.")
                    break
                    
                # Format: 4s I : Chunk ID, Chunk Data Size
                chunk_id, sub_chunk_size = struct.unpack('<4sI', chunk_header)
                
                try:
                    chunk_id_str = chunk_id.decode('ascii').strip()
                except UnicodeDecodeError:
                    chunk_id_str = f"INVALID ({chunk_id.hex()})"

                current_offset = f.tell()
                
                print(f"\n--- Chunk Found: '{chunk_id_str}' (Size: {sub_chunk_size} bytes, Offset: {current_offset}) ---")
                
                chunk_data = f.read(sub_chunk_size)
                
                if len(chunk_data) < sub_chunk_size:
                     print(f"Warning: Reached EOF while reading chunk data for '{chunk_id_str}'. Expected {sub_chunk_size} bytes, read {len(chunk_data)}.")
                     break 

                # --- Core Audio Format ('fmt ') Parsing ---
                if chunk_id_str == 'fmt ':
                    # Use struct to parse the 'fmt ' chunk data (16 bytes minimum)
                    # <H: wFormatTag, <H: nChannels, <I: nSamplesPerSec,
                    # <I: nAvgBytesPerSec, <H: nBlockAlign, <H: wBitsPerSample
                    
                    if sub_chunk_size < 16:
                         print("Warning: 'fmt ' chunk is too small. Skipping detailed parse.")
                         continue

                    fmt_data = struct.unpack('<HHIIHH', chunk_data[:16])
                    
                    audio_format, nchannels, framerate, byte_rate, block_align, bit_depth = fmt_data
                    
                    # Common Format Tag (1=PCM) lookup
                    format_name = "Linear PCM" if audio_format == 1 else f"Unknown ({audio_format})"
                    
                    print("\n[Parsed Audio Format Chunk ('fmt ')]")
                    print(f"-> Audio Format (wFormatTag):  {format_name}")
                    print(f"-> Channels (nChannels):       {nchannels} (Mono=1, Stereo=2)")
                    print(f"-> Sample Rate (Hz):           {framerate}")
                    print(f"-> Bit Depth (wBitsPerSample): {bit_depth} bits")
                    print(f"-> Byte Rate:                  {byte_rate} bytes/sec")
                    print(f"-> Block Align:                {block_align} bytes (bytes per sample frame)")
                    
                    # Dump the format chunk data for inspection
                    #hex_dump(chunk_data, "Format Chunk Data")


                # --- Data Chunk Handling ---
                elif chunk_id_str == 'data':
                    # Calculate duration if 'fmt ' was successfully parsed earlier
                    try:
                        nframes = sub_chunk_size // block_align
                        duration_seconds = nframes / framerate
                        print(f"-> Contains raw audio samples.")
                        print(f"-> Total Frames: {nframes}")
                        print(f"-> Duration: {duration_seconds:.2f} seconds (assuming previous 'fmt ' was read)")
                    except NameError:
                        print("-> Contains raw audio samples. (Duration not calculated: 'fmt ' not parsed)")
                        
                    # We don't dump the massive audio data chunk
                    print("-> Not dumping raw audio content.")

                # --- Metadata Chunk Handling (e.g., 'LIST') ---
                elif chunk_id_str == 'LIST':
                    # LIST chunks contain another 4-byte ID (e.g., 'INFO', 'adtl')
                    list_type = chunk_data[:4].decode('ascii', 'ignore').strip()
                    print(f"-> Type: {list_type} Metadata List (Common for text tags)")
                    #hex_dump(chunk_data, f"LIST - {list_ype} Metadata")
                    
                # --- Unknown/Other Chunk Handling (e.g., 'bext', 'cue ', etc.) ---
                else:
                    # Dump any other chunk's content
                    print(f"Other chunk: {chunk_id_str}")
                    #hex_dump(chunk_data, f"Chunk: {chunk_id_str}")
                    print("Bytes left: " + str(f.tell() - current_offset))
                    

                # RIFF chunks must be aligned on a 2-byte boundary (even address).
                # If the chunk size is odd, read the padding byte.
                if sub_chunk_size % 2 != 0:
                    padding = f.read(1)
                    if padding and len(padding) == 1:
                        print(f"-> Padding byte (0x{padding[0]:02X}) consumed.")
                    else:
                        print("Warning: Expected padding byte but reached EOF unexpectedly.")
                        break

        print("\n--- Parsing Complete ---")

    except struct.error as e:
        print(f"\nError: Data parsing failed (struct error). File structure unexpected. Details: {e}")
    except ValueError as e:
        print(f"\nError: RIFF structure check failed. Details: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

def main():
    # Ensure a filepath argument is provided
    if len(sys.argv) < 2:
        print("Usage: python wav_parser.py <path_to_wav_file>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    parse_wav_file(filepath)

if __name__ == "__main__":
    main()
