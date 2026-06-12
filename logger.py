import serial
import csv
import time
import os

# --- Configuration ---
SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200
OUTPUT_DIR = 'data'
OUTPUT_FILE = 'abnormal.csv'
COLLECTION_TIME_SECONDS = 15

# Create the data folder if it doesn't exist
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

file_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

print(f"Attempting to open {SERIAL_PORT} at {BAUD_RATE} baud...")

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
except Exception as e:
    print(f"Error: {e}")
    print("If you got a 'Permission denied' error, run the script with: sudo python3 logger.py")
    exit()

print(f"Success! Collecting baseline data for {COLLECTION_TIME_SECONDS} seconds...")
print(f"Saving to {file_path}")

start_time = time.time()
buffer_count = 0

with open(file_path, mode='w', newline='') as f:
    writer = csv.writer(f)
    
    while (time.time() - start_time) < COLLECTION_TIME_SECONDS:
        if ser.in_waiting > 0:
            # Read the line and decode it
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            if line:
                # Split by comma and remove empty strings (because of our trailing comma in C)
                values = [v for v in line.split(',') if v]
                
                # NanoEdge AI Studio loves rows of exactly 256 samples
                if len(values) == 256:
                    writer.writerow(values)
                    buffer_count += 1
                    if buffer_count % 10 == 0:
                        print(f"Captured {buffer_count} data buffers...")
                else:
                    print(f"Skipped a misaligned data frame (length: {len(values)})")

ser.close()
print(f"\nDone! Captured {buffer_count} total buffers.")
print(f"Your NanoEdge AI training file is ready at: {file_path}")
