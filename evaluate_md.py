import sys
import re
import json

def evaluate_markdown(md_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()

    lines = text.split('\n')
    
    # 1. Structural Integrity
    # Metrics: Count of headers, lists, and table rows.
    # Penalty: Overuse of <br> which indicates merged cells/poor table extraction instead of proper rows.
    headers = len([l for l in lines if re.match(r'^#{1,6}\s', l)])
    lists = len([l for l in lines if re.match(r'^[\-\*\+]\s', l)])
    table_rows = len([l for l in lines if l.strip().startswith('|') and l.strip().endswith('|')])
    br_count = text.count('<br>')
    
    # Base structure score based on recognizing standard markdown elements
    # Datasheets are large, so we expect hundreds of these
    struct_score = 6.0
    if headers > 50: struct_score += 1.0
    if lists > 100: struct_score += 1.0
    if table_rows > 500: struct_score += 2.0
    
    # Penalty for relying on <br> instead of true markdown structure
    struct_penalty = min(4.0, br_count / 1000.0)
    struct_score -= struct_penalty
    struct_score = max(1.0, min(10.0, struct_score))
    
    # 2. Content Completeness
    # Metrics: Word count, and instances of explicit omission.
    words = len(text.split())
    omissions = text.count("intentionally omitted")
    
    content_score = 10.0
    # Penalty for excessive dropped content
    content_score -= min(5.0, omissions / 50.0)
    # Sanity check for minimum words
    if words < 20000:
        content_score -= 5.0
    elif words < 50000:
        content_score -= 2.0
    content_score = max(1.0, min(10.0, content_score))
    
    # 3. Readability
    # Metrics: Clean register tables (R/W, U-0) and lack of repeating boilerplate noise.
    register_rw = text.count('R/W')
    register_u = text.count('U-0')
    
    noise_patterns = [
        r'©\s*\d{4}.*Microchip',
        r'DS\d+[A-Z]+-page',
        r'Advance Information',
        r'Preliminary'
    ]
    noise_count = sum(len(re.findall(p, text, flags=re.IGNORECASE)) for p in noise_patterns)
    
    # High readability means we can read register bitfields clearly
    read_score = 6.0
    if register_rw > 100: read_score += 1.0
    if register_u > 50: read_score += 1.0
    if register_rw > 300 and register_u > 100: read_score += 2.0
    
    # Penalize boilerplate running text
    noise_penalty = min(5.0, noise_count / 150.0)
    read_score -= noise_penalty
    
    read_score = max(1.0, min(10.0, read_score))
    
    return {
        "Structural Integrity": round(struct_score, 1),
        "Content Completeness": round(content_score, 1),
        "Readability": round(read_score, 1),
        "_stats": {
            "words": words,
            "headers": headers,
            "lists": lists,
            "table_rows": table_rows,
            "br_count": br_count,
            "omissions": omissions,
            "register_rw_count": register_rw,
            "noise_count": noise_count
        }
    }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python evaluate.py <path_to_md>")
        sys.exit(1)
        
    path = sys.argv[1]
    res = evaluate_markdown(path)
    print(json.dumps(res, indent=2))
