import struct
import os
import csv
from typing import List, Tuple, Dict

# --- Constants for RIFF/WAV Chunks ---
RIFF_CHUNK_ID = b'RIFF'
WAVE_FORMAT_ID = b'WAVE'
DATA_CHUNK_ID = b'data'
CUE_CHUNK_ID = b'cue '
LIST_CHUNK_ID = b'LIST'
LABL_CHUNK_ID = b'labl'
INFO_ID = b'adtl' # ID for the LIST chunk containing labels


def read_cue_points_csv(csv_filepath: str) -> List[Tuple[str, int]]:
    """Reads a CSV file containing label names and sample offsets."""
    cue_data = []
    try:
        with open(csv_filepath, mode='r', newline='') as file:
            reader = csv.DictReader(file, fieldnames=['Label', 'Offset'])
            # Skip header if present, or just assume the first row is data
            for i, row in enumerate(reader):
                # Simple check to skip headers if they match the fieldnames
                if row.get('Label', '').lower() == 'label' and i == 0:
                    continue
                
                label = row['Label'].strip()
                try:
                    # The offset must be an integer sample number
                    offset = int(row['Offset'].strip())
                    cue_data.append((label, offset))
                except ValueError:
                    print(f"Skipping row with invalid offset: {row['Offset']}")
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_filepath}")
        raise
    except Exception as e:
        print(f"An error occurred while reading CSV: {e}")
        raise
        
    return cue_data

def write_cue_points_csv(csv_filepath: str, cue_points: List[Tuple[str, int]]):
    """Writes cue points (Label, Offset) to a CSV file."""
    try:
        with open(csv_filepath, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Label', 'Offset'])
            writer.writerows(cue_points)
        print(f"\nSuccessfully exported {len(cue_points)} cue points to: {csv_filepath}")
    except Exception as e:
        print(f"Error writing CSV file: {e}")


def build_cue_chunk(cue_points: List[Tuple[str, int]]) -> bytes:
    """
    Builds the binary data for the 'cue ' chunk.
    This chunk defines the sample offsets for each cue point.
    """
    cue_count = len(cue_points)
    
    # Header: Chunk ID (4s) and Size (I) will be added later
    # Cue Count (I)
    cue_data = struct.pack('<I', cue_count) 
    
    for i, (_, offset) in enumerate(cue_points):
        # Each cue entry is 24 bytes (5x DWORD/I, 1x 4-byte ID/4s)
        cue_id = i + 1              # ID (DWORD)
        position = 0                # Play position (DWORD, must be 0 for WAVE files)
        chunk_id = DATA_CHUNK_ID    # Chunk ID (4s, usually 'data')
        chunk_start = 0             # Chunk Start (DWORD, must be 0 for WAVE files)
        frame_offset = offset       # Sample Offset (DWORD, the actual cue point)

        cue_data += struct.pack('<II4sII', 
                                cue_id, 
                                position, 
                                chunk_id, 
                                chunk_start, 
                                frame_offset)
    
    # Prepend the chunk ID and size
    chunk_size = len(cue_data)
    cue_chunk = struct.pack('<4sI', CUE_CHUNK_ID, chunk_size) + cue_data
    
    # RIFF chunks must be padded to an even number of bytes
    if chunk_size % 2 != 0:
        cue_chunk += b'\x00'
        
    return cue_chunk


def build_list_chunk(cue_points: List[Tuple[str, int]]) -> bytes:
    """
    Builds the binary data for the 'LIST' chunk containing 'labl' sub-chunks.
    This chunk defines the human-readable names for each cue point.
    """
    list_sub_chunks = struct.pack('<4s', INFO_ID) # LIST Type ID: 'adtl' (Associated Data List)
    
    for i, (label, _) in enumerate(cue_points):
        cue_id = i + 1
        # Encode label as ASCII. Some software only supports ASCII here.
        label_bytes = label.encode('ascii', errors='replace') 
        
        # labl chunk data includes: Cue ID (I) + Label bytes + Null Terminator (1 byte)
        labl_data = struct.pack('<I', cue_id) + label_bytes + b'\x00'
        
        # RIFF chunks must be padded to an even number of bytes
        labl_size = len(labl_data)
        if labl_size % 2 != 0:
            labl_data += b'\x00'
            labl_size += 1
            
        # Prepend the 'labl' chunk ID and padded size
        labl_chunk = struct.pack('<4sI', LABL_CHUNK_ID, labl_size) + labl_data
        
        list_sub_chunks += labl_chunk

    # Prepend the 'LIST' chunk ID and total size of sub-chunks
    list_chunk_size = len(list_sub_chunks)
    list_chunk = struct.pack('<4sI', LIST_CHUNK_ID, list_chunk_size) + list_sub_chunks
    
    return list_chunk


def add_cue_points_to_wav(input_wav: str, output_wav: str, csv_filepath: str):
    """
    Reads a WAV file, appends the cue and LIST chunks based on CSV data, 
    and writes the output.
    """
    if not os.path.exists(input_wav):
        print(f"Error: Input WAV file not found at {input_wav}")
        return

    # 1. Read cue points from CSV
    try:
        cue_points = read_cue_points_csv(csv_filepath)
        if not cue_points:
            print("No cue points found in CSV. Exiting.")
            return
    except Exception as e:
        print(f"Failed to read cue points from CSV: {e}")
        return

    # 2. Build new chunks
    cue_chunk_data = build_cue_chunk(cue_points)
    list_chunk_data = build_list_chunk(cue_points)
    
    new_chunks = cue_chunk_data + list_chunk_data
    new_chunks_size = len(new_chunks)

    # 3. Read existing WAV data
    try:
        with open(input_wav, 'rb') as f:
            wav_content = f.read()
    except Exception as e:
        print(f"Error reading input WAV file: {e}")
        return

    # 4. Find insertion point and update RIFF header
    
    # The RIFF header is always the first 8 bytes: 'RIFF' (4s) + File Size (I)
    riff_header_id = wav_content[0:4]
    if riff_header_id != RIFF_CHUNK_ID:
        print("Error: File does not appear to be a RIFF file.")
        return

    # Extract original total file size (bytes 4-7)
    original_size_bytes = wav_content[4:8]
    original_file_size, = struct.unpack('<I', original_size_bytes)

    # Calculate new total file size (size of RIFF data block, excluding 'RIFF' and the size field itself)
    new_file_size = original_file_size + new_chunks_size
    new_size_bytes = struct.pack('<I', new_file_size)

    # We append the new chunks to the end of the file content
    # and overwrite the size in the RIFF header.
    
    # New WAV content: RIFF ID (4s) + New Size (I) + Rest of original content + New Chunks
    new_wav_content = RIFF_CHUNK_ID + new_size_bytes + wav_content[8:] + new_chunks
    
    # 5. Write the new WAV content to the output file
    try:
        with open(output_wav, 'wb') as f:
            f.write(new_wav_content)
        print(f"Successfully wrote new WAV file with cue points to: {output_wav}")
        print(f"Added {len(cue_points)} cue points.")
    except Exception as e:
        print(f"Error writing output WAV file: {e}")


def parse_cue_chunk(cue_data: bytes) -> Dict[int, int]:
    """Parses the 'cue ' chunk data (ID and offset)."""
    cue_points = {}
    
    # Read cue count (4 bytes at start of data)
    cue_count, = struct.unpack('<I', cue_data[:4])
    
    # Each cue point is 24 bytes, starting after the 4-byte count
    offset = 4
    for _ in range(cue_count):
        # Format: <II4sII (ID, Position, Chunk ID, Chunk Start, Frame Offset)
        # We only care about ID (I) and Frame Offset (I)
        cue_id, position, chunk_id, chunk_start, frame_offset = struct.unpack('<II4sII', cue_data[offset:offset + 24])
        cue_points[cue_id] = frame_offset
        offset += 24
        
    return cue_points

def parse_list_labl_chunks(list_data: bytes) -> Dict[int, str]:
    """Parses the 'LIST' chunk data, specifically 'adtl'/'labl' sub-chunks."""
    labels = {}
    
    # Check if this is the correct LIST type ('adtl' for cue point labels)
    list_type = list_data[0:4]
    if list_type != INFO_ID: # INFO_ID = b'adtl'
        return labels 

    offset = 4 # Start looking for sub-chunks after the 4-byte LIST type ('adtl')
    data_size = len(list_data)
    
    while offset < data_size:
        # Read sub-chunk ID (4s) and size (I)
        # Ensure we have enough bytes for the header
        if offset + 8 > data_size:
            break
            
        sub_chunk_id, sub_chunk_size = struct.unpack('<4sI', list_data[offset:offset + 8])
        sub_chunk_data_start = offset + 8
        
        if sub_chunk_id == LABL_CHUNK_ID: # b'labl'
            # labl data starts with Cue ID (I)
            cue_id, = struct.unpack('<I', list_data[sub_chunk_data_start:sub_chunk_data_start + 4])
            
            # The label text starts 4 bytes in and ends at the null terminator
            label_bytes = list_data[sub_chunk_data_start + 4: sub_chunk_data_start + sub_chunk_size]
            
            # Find the null terminator (b'\x00')
            try:
                null_index = label_bytes.index(b'\x00')
                label = label_bytes[:null_index].decode('ascii')
                labels[cue_id] = label
            except ValueError:
                # Handle missing null terminator, ignoring decode errors
                label = label_bytes.decode('ascii', errors='ignore').strip()
                labels[cue_id] = label
        
        # Advance offset by chunk header (8 bytes) + chunk size + padding
        offset += 8 + sub_chunk_size
        if sub_chunk_size % 2 != 0:
            offset += 1 # Handle padding
            
    return labels


def read_cue_points_from_wav(wav_filepath: str) -> List[Tuple[str, int]]:
    """Reads cue points from a WAV file and returns a list of (label, offset) tuples."""
    if not os.path.exists(wav_filepath):
        print(f"Error: WAV file not found at {wav_filepath}")
        return []
    
    cue_chunk_data = None
    list_chunk_data = None
    
    try:
        with open(wav_filepath, 'rb') as f:
            # Check RIFF header and skip overall file size and WAVE format ID
            riff_chunk_id = f.read(4)
            file_size_bytes = f.read(4)
            wave_format_id = f.read(4)
            
            if riff_chunk_id != RIFF_CHUNK_ID or len(file_size_bytes) < 4 or wave_format_id != WAVE_FORMAT_ID:
                print("Error: File is not a valid RIFF/WAVE file.")
                return []
            
            # Chunk reading loop
            while True:
                header = f.read(8)
                if len(header) < 8:
                    break # End of file
                
                chunk_id, chunk_size = struct.unpack('<4sI', header)
                
                # Read chunk data
                chunk_data = f.read(chunk_size)
                
                if chunk_id == CUE_CHUNK_ID:
                    cue_chunk_data = chunk_data
                elif chunk_id == LIST_CHUNK_ID:
                    # Check if it's the 'adtl' LIST chunk by inspecting the first 4 bytes of data
                    if chunk_data[:4] == INFO_ID:
                        list_chunk_data = chunk_data
                
                # RIFF chunks are padded to the next even byte boundary
                if chunk_size % 2 != 0:
                    f.seek(1, 1) # Skip padding byte
                    
                if cue_chunk_data and list_chunk_data:
                    break # Found both required chunks, stop reading
        
    except Exception as e:
        print(f"Error reading WAV file chunks: {e}")
        return []

    # 2. Parse the found chunks
    if not cue_chunk_data:
        print("Cue points not found ('cue ' chunk missing).")
        return []
        
    cue_offsets_by_id = parse_cue_chunk(cue_chunk_data)
    cue_labels_by_id = {}
    
    if list_chunk_data:
        cue_labels_by_id = parse_list_labl_chunks(list_chunk_data)
    else:
        print("Cue point labels not found ('LIST'/'adtl'/'labl' chunks missing). Using default labels.")

    # 3. Combine and sort results by ID/Offset
    combined_cue_points = []
    
    # Iterate through IDs present in the cue chunk (the definitive list of cues)
    for cue_id, offset in cue_offsets_by_id.items():
        # Fallback label if LIST chunk is missing or incomplete
        label = cue_labels_by_id.get(cue_id, f"Cue {cue_id}") 
        combined_cue_points.append((label, offset))
        
    # Sort by the offset for a cleaner CSV output
    combined_cue_points.sort(key=lambda x: x[1])
    
    return combined_cue_points


# --- Example Usage ---

if __name__ == "__main__":
    
    # Configuration
    # Set this mode to 'WRITE' to add cues to a WAV (reads CSV), 
    # or 'READ' to extract cues from a WAV (writes CSV).
    OPERATION_MODE = 'WRITE' 

    # !!! IMPORTANT !!!
    # REPLACE 'input.wav' with the path to an actual, valid WAV file.
    INPUT_WAV_FILE = 'input.wav'
    OUTPUT_WAV_FILE = 'output_with_cues.wav'
    CSV_FILE = 'cue_points.csv'
    
    if OPERATION_MODE == 'WRITE':
        # --- WRITE MODE: Read CSV, Add cues to INPUT_WAV_FILE, Write to OUTPUT_WAV_FILE ---
        if os.path.exists(INPUT_WAV_FILE):
            print(f"--- Running in WRITE Mode (Importing cues from {CSV_FILE}) ---")
            add_cue_points_to_wav(INPUT_WAV_FILE, OUTPUT_WAV_FILE, CSV_FILE)
        else:
            print("-" * 50)
            print(f"WARNING: '{INPUT_WAV_FILE}' not found. Cannot run WRITE mode.")
            print("Create a test 'input.wav' and the generated 'cue_points.csv' to proceed.")
            print("-" * 50)
            
    elif OPERATION_MODE == 'READ':
        # --- READ MODE: Read cues from INPUT_WAV_FILE, Write to CSV_FILE ---
        print(f"--- Running in READ Mode (Exporting cues to {CSV_FILE}) ---")
        extracted_cues = read_cue_points_from_wav(INPUT_WAV_FILE)
        if extracted_cues:
            write_cue_points_csv(CSV_FILE, extracted_cues)
        else:
            print(f"No cues were extracted from {INPUT_WAV_FILE}.")
            
    else:
        print("Invalid OPERATION_MODE. Set to 'WRITE' or 'READ' in the script's main block.")
