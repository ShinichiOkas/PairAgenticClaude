"""Survey s:/work/develop projects for language/LLM library preferences."""
import os, re
from pathlib import Path
from collections import defaultdict

ROOT = Path("s:/work/develop")

LANG_EXTS = {
    'Python': ['.py'],
    'TypeScript': ['.ts', '.tsx'],
    'JavaScript': ['.js', '.jsx', '.mjs'],
    'Go': ['.go'],
    'Rust': ['.rs'],
}

LLM_PATTERNS = [
    (r'anthropic', 'anthropic'),
    (r'openai', 'openai'),
    (r'langchain', 'langchain'),
    (r'llama.?index|llamaindex', 'llamaindex'),
    (r'google[.\-]generativeai|import genai', 'google-generativeai'),
    (r'transformers', 'transformers(HF)'),
    (r'litellm', 'litellm'),
    (r'ollama', 'ollama'),
    (r'groq', 'groq'),
    (r'mistralai', 'mistral'),
    (r'cohere', 'cohere'),
    (r'replicate', 'replicate'),
    (r'together', 'together-ai'),
    (r'boto3.*bedrock|bedrock.*boto3', 'AWS Bedrock'),
    (r'vertexai|vertex_ai', 'Vertex AI'),
]

MODEL_PATTERNS = [
    r'claude-[a-z0-9\-\.]{3,30}',
    r'gpt-[a-z0-9\-\.]{2,20}',
    r'gemini-[a-z0-9\-\.]{2,20}',
    r'o[13]-[a-z0-9\-\.]{2,20}',
]

SKIP_DIRS = {'venv', '.venv', 'node_modules', '.git', '__pycache__', 'dist', 'build', '.tox', 'env'}

def scan_project(proj_path):
    langs = defaultdict(int)
    libs = set()
    models = set()

    # requirements.txt / pyproject.toml / package.json
    for depfile in ['requirements.txt', 'pyproject.toml', 'package.json', 'Pipfile']:
        f = proj_path / depfile
        if f.exists():
            try:
                content = f.read_text(errors='ignore').lower()
                for pat, name in LLM_PATTERNS:
                    if re.search(pat, content, re.IGNORECASE):
                        libs.add(name)
            except:
                pass

    # Source files
    for ext_group, exts in LANG_EXTS.items():
        for ext in exts:
            count = 0
            for f in proj_path.rglob(f'*{ext}'):
                if any(s in f.parts for s in SKIP_DIRS):
                    continue
                langs[ext_group] += 1
                count += 1
                if count > 200:
                    break
                try:
                    content = f.read_text(errors='ignore')
                    for pat, name in LLM_PATTERNS:
                        if re.search(pat, content, re.IGNORECASE):
                            libs.add(name)
                    for mp in MODEL_PATTERNS:
                        for m in re.findall(mp, content, re.IGNORECASE):
                            models.add(m.lower())
                except:
                    pass

    return dict(langs), sorted(libs), sorted(models)

print(f"Scanning {ROOT} ...\n")
all_langs = defaultdict(int)
all_libs = defaultdict(int)
all_models = defaultdict(int)
per_project = {}

for proj in sorted(ROOT.iterdir()):
    if not proj.is_dir() or proj.name.startswith('.'):
        continue
    langs, libs, models = scan_project(proj)
    if not langs and not libs:
        continue
    per_project[proj.name] = {'langs': langs, 'libs': libs, 'models': models}
    for lang, cnt in langs.items():
        all_langs[lang] += cnt
    for lib in libs:
        all_libs[lib] += 1
    for m in models:
        all_models[m] += 1
    print(f"  {proj.name:30s}  langs={list(langs.keys())}  libs={libs}")

print("\n" + "="*60)
print("LANGUAGES (total files across projects):")
for lang, cnt in sorted(all_langs.items(), key=lambda x: -x[1]):
    print(f"  {lang:20s} {cnt:4d} files")

print("\nLLM LIBRARIES (# projects using):")
for lib, cnt in sorted(all_libs.items(), key=lambda x: -x[1]):
    print(f"  {lib:30s} {cnt:3d} projects")

print("\nMODEL IDs FOUND (# occurrences):")
for m, cnt in sorted(all_models.items(), key=lambda x: -x[1])[:30]:
    print(f"  {m:40s} {cnt:3d}")
