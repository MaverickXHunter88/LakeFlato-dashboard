from datetime import datetime, timedelta 
import os
import json
import csv

base_path = os.path.expanduser("~")

now=datetime.now()

today = now.strftime("%Y-%m-%d")
yesterday=(now - timedelta(days=1)).strftime("%Y-%m-%d")

input_files = [
	os.path.join(base_path, f"data_log_{yesterday}.jsonl"),
	os.path.join(base_path, f"data_log_{today}.jsonl"),
]	

output_file="/home/designperformancelf/data_log.csv"

all_rows = []
all_keys = set()

#Step 1: Read Everything and Collect all Keys
for input_file in input_files:
	if not os.path.exists(input_file):
		continue
	
	with open(input_file, "r") as infile:
		for line in infile:
			line = line.strip()
			if not line:
				continue
		
			data = json.loads(line)
			all_rows.append(data)
			all_keys.update(data.keys())

#Sort Rows by timestamp (ensures correct order)
all_rows = sorted(all_rows, key=lambda x: x.get("timestamp",""))

cutoff= datetime.now() - timedelta(days=2)

def is_recent(row):
	try:
		return datetime.fromisoformat(row["timestamp"]) > cutoff
	except:
		return False

all_rows = [r for r in all_rows if is_recent(r)]

#Step 2 Write CSV with Full Schema
with open(output_file, "w", newline="") as outfile:
	writer = csv.DictWriter(outfile, fieldnames=sorted(all_keys))
	writer.writeheader()
	
	for row in all_rows:
		writer.writerow(row)
			
print("Converted JSONL to CSV") 
