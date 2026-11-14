import os

results = []
for root, dirs, files in os.walk('app'):
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
                for idx, line in enumerate(fp, 1):
                    if 'Workout.query' in line:
                        results.append(f"{p}:{idx}: {line.strip()}")

for r in results:
    print(r)
