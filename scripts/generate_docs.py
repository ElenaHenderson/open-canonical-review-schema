#!/usr/bin/env python3
"""Build the GitHub Pages site: schema docs, plus every released schema version.

Each release's schema files are kept in `versions/v<version>/` and published at
`<site>/v<version>/<file>`, the URL in that schema's `$id`.
"""

import shutil
from pathlib import Path

from json_schema_for_humans.generate import generate_from_filename
from json_schema_for_humans.generation_configuration import GenerationConfiguration


def stroke_icon(paths: str) -> str:
    return (
        '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" '
        f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'
    )


def logo(src: str) -> str:
    return f'<img src="{src}" alt="">'


def badge(text: str, background: str, color: str = "#fff", underline: str = "") -> str:
    """A square of a site's own colors, for a system with no logo that works at icon size."""
    style = f"background: {background}; color: {color}"
    if underline:
        style += f"; box-shadow: inset 0 -3px 0 {underline}"
    return f'<span class="site-badge" style="{style}">{text}</span>'


# Google publishes no Deep Review logo, so DeepReview shows Google's, from Google's own CDN.
GOOGLE_LOGO = "https://www.gstatic.com/images/branding/product/2x/googleg_48dp.png"

# The review sources drawn flowing into OCRS, in order: name, group, what it gives, icon.
# Logos are in site/logos/. OpenReview, CMT and HotCRP have no logo legible at icon size, so
# their icons are in their sites' own colors; ScholarOne's is the book cropped from its wordmark.
SOURCES = [
    ("OpenReview", "conference", "API note", badge("OR", "#8c1b13")),
    ("CMT", "conference", "export", badge("CMT", "#007ea3")),
    ("HotCRP", "conference", "review JSON", badge("H", "#ffbbbb", "#f33360", "#f33360")),
    ("Editorial Manager", "journal", "export", logo("logos/editorialmanager.png")),
    (
        "ScholarOne",
        "journal",
        "export",
        f'<span class="crop">{logo("logos/scholarone.png")}</span>',
    ),
    (
        "Journal narrative",
        "journal",
        "full_text",
        stroke_icon('<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 16h6"/>'),
    ),
    ("OpenAI<wbr>Review", "ai", "paper.json", logo("logos/openaireview.png")),
    ("Reviewer3", "ai", "report", logo("logos/reviewer3.png")),
    ("DeepReview", "ai", "report.md", logo(GOOGLE_LOGO)),
]
# The groups the sources meet in on the way: key, name, referee type, color, icon.
GROUPS = [
    (
        "conference",
        "Conference",
        "referee: human",
        "#e11d48",
        stroke_icon(
            '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/>'
            '<path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.2a6.5 6.5 0 0 1 3.5 5.8"/>'
        ),
    ),
    (
        "journal",
        "Journal",
        "referee: human",
        "#2563eb",
        stroke_icon(
            '<path d="M2.5 4.5h6a3.5 3.5 0 0 1 3.5 3.5v12a3 3 0 0 0-3-3H2.5z"/>'
            '<path d="M21.5 4.5h-6A3.5 3.5 0 0 0 12 8v12a3 3 0 0 1 3-3h6.5z"/>'
        ),
    ),
    (
        "ai",
        "AI reviewers",
        "referee: ai",
        "#7c3aed",
        stroke_icon(
            '<path d="M10 3.5l1.8 4.7 4.7 1.8-4.7 1.8L10 16.5l-1.8-4.7L3.5 10l4.7-1.8z"/>'
            '<path d="M18 14l.9 2.1 2.1.9-2.1.9L18 20l-.9-2.1-2.1-.9 2.1-.9z"/>'
        ),
    ),
]
OCRS_ICON = (
    '<svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round">'
    '<path d="M4 4.5 12 19.5M12 4.5v15M20 4.5 12 19.5" fill="none"/>'
    '<circle cx="4" cy="4.5" r="2.2"/><circle cx="12" cy="4.5" r="2.2"/>'
    '<circle cx="20" cy="4.5" r="2.2"/><circle cx="12" cy="19.5" r="3.2"/></svg>'
)


def main():
    """Generate HTML documentation for all schemas."""
    root = Path(__file__).parent.parent
    schemas_dir = root / "src" / "ocrs" / "schemas"
    docs_dir = root / "docs"

    # Ensure docs directory exists
    docs_dir.mkdir(exist_ok=True)

    # Configuration for json-schema-for-humans
    config = GenerationConfiguration(
        template_name="js_offline",
        expand_buttons=True,
        show_breadcrumbs=True,
        collapse_long_descriptions=False,
        link_to_reused_ref=True,
        show_toc=True,
        with_footer=True,
    )

    # Generate docs for the main JSON Schema
    # Note: metric-catalog and mapping-spec are data files, not JSON Schemas
    schema_file = "canonical-review.schema.json"
    output_file = "canonical-review.html"
    schema_path = schemas_dir / schema_file
    output_path = docs_dir / output_file

    print(f"Generating {output_file} from {schema_file}...")
    generate_from_filename(schema_path, output_path, config=config)

    shutil.copytree(root / "site", docs_dir, dirs_exist_ok=True)

    versions = sorted(path.name for path in (root / "versions").iterdir() if path.is_dir())
    for version in versions:
        shutil.copytree(root / "versions" / version, docs_dir / version, dirs_exist_ok=True)

    # Create the landing page
    create_landing_page(docs_dir, versions)

    # Create .nojekyll to prevent GitHub Pages from using Jekyll
    (docs_dir / ".nojekyll").touch()

    print(f"\nDocumentation generated in {docs_dir}")
    print("To preview locally: python -m http.server 8000 --directory docs")


def create_landing_page(docs_dir: Path, versions: list[str]):
    """Create a landing page linking to all schema docs."""
    landing_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OCRS - Open Canonical Review Schema</title>
    <style>
        :root {
            --bg-color: #1a1a2e;
            --card-bg: #16213e;
            --primary: #0f3460;
            --accent: #e94560;
            --text: #eaeaea;
            --text-muted: #a0a0a0;
        }
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: var(--bg-color);
            color: var(--text);
            min-height: 100vh;
            padding: 2rem;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        header {
            text-align: center;
            margin-bottom: 3rem;
        }
        h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, var(--accent), #ff6b6b);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .subtitle {
            color: var(--text-muted);
            font-size: 1.1rem;
        }
        .intro {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            border: 1px solid var(--primary);
        }
        .intro p {
            color: var(--text-muted);
            line-height: 1.8;
        }
        .schemas {
            display: grid;
            gap: 1.5rem;
        }
        .schema-card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 1.5rem;
            border: 1px solid var(--primary);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .schema-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 24px rgba(233, 69, 96, 0.2);
        }
        .schema-card h2 {
            font-size: 1.3rem;
            margin-bottom: 0.5rem;
        }
        .schema-card h2 a {
            color: var(--text);
            text-decoration: none;
        }
        .schema-card h2 a:hover {
            color: var(--accent);
        }
        .schema-card p {
            color: var(--text-muted);
            line-height: 1.6;
        }
        .badge {
            display: inline-block;
            background: var(--primary);
            color: var(--accent);
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.8rem;
            margin-top: 1rem;
        }
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }
        .feature {
            background: rgba(15, 52, 96, 0.3);
            padding: 0.75rem;
            border-radius: 8px;
            font-size: 0.9rem;
            color: var(--text-muted);
        }
        .feature strong {
            color: var(--accent);
        }
        footer {
            text-align: center;
            margin-top: 3rem;
            color: var(--text-muted);
            font-size: 0.9rem;
        }
        footer a {
            color: var(--accent);
            text-decoration: none;
        }
        .flow {
            --line: #dcdcdc;
            position: relative;
            margin-bottom: 3rem;
            padding: 3.5rem 1.5rem 3rem;
            border-radius: 16px;
            background: #fafafa;
            color: #171717;
        }
        .flow-lines {
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            overflow: visible;
            pointer-events: none;
        }
        .flow-lines path {
            fill: none;
            stroke: var(--line);
            stroke-width: 1;
            transition: stroke 0.2s;
        }
        .flow-row {
            position: relative;
            list-style: none;
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .flow-leaves {
            grid-template-columns: repeat(9, minmax(0, 1fr));
            gap: 0.25rem;
        }
        .flow-groups {
            margin-top: 5.5rem;
        }
        .node {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
        }
        .node-icon {
            width: 28px;
            height: 28px;
            display: grid;
            place-items: center;
            margin-bottom: 0.55rem;
            color: #525252;
        }
        .node-icon img {
            display: block;
            max-width: 28px;
            max-height: 28px;
            mix-blend-mode: multiply;
        }
        .node-icon .crop {
            width: 15px;
            height: 28px;
            overflow: hidden;
        }
        .node-icon .crop img {
            height: 28px;
            max-width: none;
        }
        .site-badge {
            width: 28px;
            height: 28px;
            border-radius: 6px;
            display: grid;
            place-items: center;
            font-size: 0.62rem;
            font-weight: 800;
            letter-spacing: -0.02em;
        }
        .node-name {
            font-size: 0.82rem;
            font-weight: 500;
            line-height: 1.25;
        }
        .node-sub {
            margin-top: 0.15rem;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.68rem;
            color: #737373;
        }
        .flow-groups .node {
            flex-direction: row;
            justify-content: center;
            gap: 0.65rem;
            text-align: left;
        }
        .flow-groups .node-icon {
            margin: 0;
            color: var(--group);
        }
        .flow-groups .node-name {
            font-size: 0.95rem;
        }
        .node-text {
            display: flex;
            flex-direction: column;
        }
        .flow-hub {
            position: relative;
            margin: 5rem auto 0;
            width: fit-content;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .hub-title {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }
        @media (max-width: 720px) {
            body {
                padding: 2rem 1rem;
            }
            .flow {
                padding: 2.5rem 0.5rem 2rem;
            }
            .flow-leaves .node-name,
            .flow-leaves .node-sub {
                position: absolute;
                width: 1px;
                height: 1px;
                overflow: hidden;
                clip-path: inset(50%);
            }
            .flow-leaves .node-icon {
                margin: 0;
            }
            .flow-groups {
                margin-top: 4rem;
            }
            .flow-groups .node {
                flex-direction: column;
                gap: 0.4rem;
                text-align: center;
            }
            .flow-groups .node-name {
                font-size: 0.8rem;
            }
            .flow-groups .node-sub {
                font-size: 0.6rem;
            }
            .flow-hub {
                margin-top: 4rem;
            }
        }
        @media (prefers-reduced-motion: reduce) {
            .flow-lines circle {
                display: none;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>OCRS</h1>
            <p class="subtitle">Open Canonical Review Schema - Documentation</p>
        </header>

        <figure class="flow" aria-label="Review sources mapped into OCRS">
            <svg class="flow-lines" aria-hidden="true"></svg>
            <ul class="flow-row flow-leaves">
FLOW_LEAVES
            </ul>
            <ul class="flow-row flow-groups">
FLOW_GROUPS
            </ul>
            <div class="flow-hub">
                <div class="hub-title">OCRS_ICON OCRS</div>
                <div class="node-sub">canonical-review LATEST_VERSION</div>
            </div>
        </figure>

        <div class="intro">
            <p>
                OCRS provides a standardized, machine-readable format for representing peer reviews
                across different platforms and systems. It enables interoperability between review
                systems like OpenReview, CMT, and journal workflows while preserving rich provenance
                information for both human and AI-generated reviews.
            </p>
        </div>

        <div class="schemas">
            <div class="schema-card">
                <h2><a href="canonical-review.html">Canonical Review Schema</a></h2>
                <p>
                    The core schema defining the structure of peer reviews in canonical form.
                </p>
                <div class="features">
                    <div class="feature"><strong>Referees:</strong> Human, AI, Hybrid</div>
                    <div class="feature"><strong>Provenance:</strong> Source tracking</div>
                    <div class="feature"><strong>Findings:</strong> Strengths, weaknesses</div>
                    <div class="feature"><strong>Metrics:</strong> Normalized scores</div>
                    <div class="feature"><strong>Decisions:</strong> Recommendations</div>
                    <div class="feature"><strong>AI Info:</strong> Models, prompts</div>
                </div>
                <span class="badge">JSON Schema Draft 2020-12</span>
            </div>
            <div class="schema-card">
                <h2>Schema files</h2>
                <ul>
VERSION_LINKS
                </ul>
            </div>
        </div>

        <footer>
            <p>
                <a href="https://github.com/valency-oss/open-canonical-review-schema">GitHub</a>
                &nbsp;&middot;&nbsp;
                Apache License 2.0
            </p>
        </footer>
    </div>
    <script>
        // Draw lines from each source down to its group, and from each group down to OCRS.
        (() => {
            const NS = "http://www.w3.org/2000/svg";
            const flow = document.querySelector(".flow");
            const svg = flow.querySelector(".flow-lines");
            const leafRow = flow.querySelector(".flow-leaves");
            const hub = flow.querySelector(".hub-title");
            const svgElement = (name, attributes) => {
                const element = document.createElementNS(NS, name);
                for (const [key, value] of Object.entries(attributes)) {
                    element.setAttribute(key, value);
                }
                return element;
            };

            // Each edge runs from the bottom of `from` to the top of `to`, each centered on `x`,
            // with a dot that travels it every `duration` seconds, starting `delay` seconds in.
            const edges = [];
            const addEdge = (from, to, color, delay, duration) => {
                const path = svgElement("path", {});
                const dot = svgElement("circle", { r: 2.5, fill: color, opacity: 0 });
                svg.append(path, dot);
                edges.push({ from, to, path, dot, delay, duration, length: 0 });
                return path;
            };

            const groups = [...flow.querySelectorAll(".flow-groups .node")];
            const colorOf = (group) => getComputedStyle(group).getPropertyValue("--group").trim();
            flow.querySelectorAll(".flow-leaves .node").forEach((leaf, i) => {
                const group = flow.querySelector(`#group-${leaf.dataset.group}`);
                const color = colorOf(group);
                const path = addEdge(
                    { box: leafRow, x: leaf }, { box: group, x: group }, color, i * 0.45, 2.6,
                );
                leaf.addEventListener("mouseenter", () => (path.style.stroke = color));
                leaf.addEventListener("mouseleave", () => (path.style.stroke = ""));
            });
            groups.forEach((group, i) => {
                const delay = 0.9 + i * 0.7;
                addEdge({ box: group, x: group }, { box: hub, x: hub }, colorOf(group), delay, 2);
            });

            const layout = () => {
                const origin = flow.getBoundingClientRect();
                svg.setAttribute("viewBox", `0 0 ${origin.width} ${origin.height}`);
                const centerX = (element) => {
                    const box = element.getBoundingClientRect();
                    return box.left + box.width / 2 - origin.left;
                };
                for (const edge of edges) {
                    const { from, to, path } = edge;
                    const x1 = centerX(from.x);
                    const y1 = from.box.getBoundingClientRect().bottom - origin.top + 10;
                    const x2 = centerX(to.x);
                    const y2 = to.box.getBoundingClientRect().top - origin.top - 10;
                    const bend = (y2 - y1) / 2;
                    const d = `M${x1},${y1} C${x1},${y1 + bend} ${x2},${y2 - bend} ${x2},${y2}`;
                    path.setAttribute("d", d);
                    edge.length = path.getTotalLength();
                }
            };
            new ResizeObserver(layout).observe(flow);
            layout();

            const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);
            const tick = (now) => {
                for (const { path, dot, delay, duration, length } of edges) {
                    const elapsed = now / 1000 - delay;
                    if (elapsed < 0) continue;
                    const t = (elapsed % duration) / duration;
                    const point = path.getPointAtLength(ease(t) * length);
                    dot.setAttribute("cx", point.x);
                    dot.setAttribute("cy", point.y);
                    dot.setAttribute("opacity", Math.min(1, t / 0.15, (1 - t) / 0.15));
                }
                requestAnimationFrame(tick);
            };
            if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
                requestAnimationFrame(tick);
            }
        })();
    </script>
</body>
</html>
"""
    version_links = "\n".join(
        f'{" " * 20}<li><a href="{version}/canonical-review.schema.json">{version}</a></li>'
        for version in reversed(versions)
    )
    flow_leaves = "\n".join(
        f'{" " * 16}<li class="node" data-group="{group}" title="{name.replace("<wbr>", "")}">'
        f'<span class="node-icon" aria-hidden="true">{icon}</span>'
        f'<span class="node-name">{name}</span><span class="node-sub">{gives}</span></li>'
        for name, group, gives, icon in SOURCES
    )
    flow_groups = "\n".join(
        f'{" " * 16}<li class="node" id="group-{key}" style="--group: {color}">'
        f'<span class="node-icon" aria-hidden="true">{icon}</span><span class="node-text">'
        f'<span class="node-name">{name}</span><span class="node-sub">{referee}</span></span></li>'
        for key, name, referee, color, icon in GROUPS
    )
    landing_html = (
        landing_html.replace("VERSION_LINKS", version_links)
        .replace("FLOW_LEAVES", flow_leaves)
        .replace("FLOW_GROUPS", flow_groups)
        .replace("OCRS_ICON", OCRS_ICON)
        .replace("LATEST_VERSION", versions[-1])
    )
    # Write as index.html - the landing page for GitHub Pages
    (docs_dir / "index.html").write_text(landing_html)


if __name__ == "__main__":
    main()
