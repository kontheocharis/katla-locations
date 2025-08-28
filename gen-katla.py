#!/usr/bin/env python3

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Union


@dataclass
class DisplaySnippet:
    name: str
    kind: Literal["display"]
    line_offset: int
    line_count: int


@dataclass
class InlineSnippet:
    name: str
    kind: Literal["inline"]
    line_offset: int
    column_start_offset: int
    column_end_offset: int


Snippet = Union[DisplaySnippet, InlineSnippet]


def parse_display_snippets(lines: List[str]) -> List[DisplaySnippet]:
    """Parse display style snippets from lines."""
    snippets: List[DisplaySnippet] = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Look for opening display tag
        display_start_match = re.match(r"^--\s*<(\w+)>\s*$", line)
        if display_start_match:
            name = display_start_match.group(1)
            start_line = i

            # Look for matching closing tag
            j = i + 1
            found_end = False
            while j < len(lines):
                end_line = lines[j].strip()
                display_end_match = re.match(
                    rf"^--\s*</{re.escape(name)}>\s*$", end_line
                )
                if display_end_match:
                    line_offset = start_line + 1  # 1-indexed
                    line_count = j - start_line - 1  # Lines between tags
                    snippets.append(
                        DisplaySnippet(
                            name=name,
                            kind="display",
                            line_offset=line_offset,
                            line_count=line_count,
                        )
                    )
                    found_end = True
                    break
                j += 1

            if not found_end:
                print(
                    f"Warning: Unclosed display tag '<{name}>' at line {start_line + 1}",
                    file=sys.stderr,
                )

        i += 1

    return snippets


def parse_inline_snippets(lines: List[str]) -> List[InlineSnippet]:
    """Parse inline style snippets from lines."""
    snippets: List[InlineSnippet] = []

    for line_idx, line in enumerate(lines):
        # Find all inline comment pairs on this line
        inline_pattern = r"\{-\s*<(\w+)>\s*-\}(.*?)\{-\s*</\1>\s*-\}"
        matches = re.finditer(inline_pattern, line)

        for match in matches:
            name = match.group(1)
            start_pos = match.start()
            end_pos = match.end()

            # Find the position right after the opening tag
            opening_tag_end = line.find("-}", start_pos) + 2
            # Find the position right before the closing tag
            closing_tag_start = line.rfind("{-", start_pos, end_pos)

            column_start_offset = opening_tag_end
            column_end_offset = closing_tag_start

            snippets.append(
                InlineSnippet(
                    name=name,
                    kind="inline",
                    line_offset=line_idx + 1,  # 1-indexed
                    column_start_offset=column_start_offset,
                    column_end_offset=column_end_offset,
                )
            )

    return snippets


def parse_file(filepath: str) -> List[Snippet]:
    """Parse an Idris file and return all snippets found."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Remove newlines but keep them for accurate parsing
        lines = [line.rstrip("\n\r") for line in lines]

        display_snippets = parse_display_snippets(lines)
        inline_snippets = parse_inline_snippets(lines)

        return display_snippets + inline_snippets

    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error parsing file '{filepath}': {e}", file=sys.stderr)
        return []


def run_katla_command(
    snippet: Snippet,
    src_file: str,
    ttm_file: str,
    dry_run: bool = False,
) -> str:
    """Run the appropriate katla command for a snippet and return the output."""
    match snippet.kind:
        case "display":
            cmd = [
                "katla",
                "latex",
                "macro",
                snippet.name,
                src_file,
                ttm_file,
                str(snippet.line_offset + 1),
                "0",
                str(snippet.line_count - 1),
            ]
        case "inline":
            cmd = [
                "katla",
                "latex",
                "macro",
                "inline",
                snippet.name,
                src_file,
                ttm_file,
                "0",
                str(snippet.line_offset),
                str(snippet.column_start_offset + 1),
                str(snippet.column_end_offset),
            ]

    if dry_run:
        print(f"Would run: {' '.join(cmd)}")
        return f"% Dry run - would generate macro for {snippet.name}\n"

    try:
        # Run katla command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(
                f"Error running katla for {snippet.name}: {result.stderr}",
                file=sys.stderr,
            )
            return f"% Error generating macro for {snippet.name}\n"

        print(f"Generated macro for {snippet.name}")
        return result.stdout

    except Exception as e:
        print(f"Error running katla command for {snippet.name}: {e}", file=sys.stderr)
        return f"% Error generating macro for {snippet.name}\n"


def print_snippet_debug(snippet: Snippet, src_file: str, lines: List[str]):
    """Print debug information about a snippet including its content."""
    print(f"Snippet: {snippet.name} ({snippet.kind})")
    print(f"  File: {src_file}")

    match snippet.kind:
        case "display":
            print(f"  Line offset: {snippet.line_offset}")
            print(f"  Line count: {snippet.line_count}")
            print("  Content:")
            start_line = (
                snippet.line_offset
            )  # Already 1-indexed, but we need 0-indexed for array access
            end_line = start_line + snippet.line_count
            for i in range(start_line, min(end_line, len(lines))):
                print(f"    {i+1}: {lines[i]}")
        case "inline":
            print(f"  Line offset: {snippet.line_offset}")
            print(f"  Column start: {snippet.column_start_offset}")
            print(f"  Column end: {snippet.column_end_offset}")
            line_content = lines[snippet.line_offset - 1]  # Convert to 0-indexed
            snippet_content = line_content[
                snippet.column_start_offset : snippet.column_end_offset
            ]
            print(f"  Line content: {line_content}")
            print(f"  Snippet content: '{snippet_content}'")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Katla helper for generating LaTeX macros based on source locations in Idris files"
    )
    parser.add_argument(
        "files", nargs="+", help="Pairs of IDRIS_SRC_FILE and IDRIS_TTM_FILE"
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        required=True,
        help="Output directory for generated LaTeX files",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Debug dry-run mode: print snippets and their contents without running katla",
    )

    args = parser.parse_args()

    # Parse file pairs
    if len(args.files) % 2 != 0:
        print(
            "Error: Files must be provided in pairs of (IDRIS_SRC_FILE, IDRIS_TTM_FILE)",
            file=sys.stderr,
        )
        sys.exit(1)

    file_pairs = [
        (args.files[i], args.files[i + 1]) for i in range(0, len(args.files), 2)
    ]

    total_success = 0
    total_snippets = 0
    all_macro_content: List[str] = []

    # Generate header for the combined file
    all_macro_content.append("% Generated LaTeX macros for all Idris files\n")
    all_macro_content.append("% Generated by gen-katla.py\n\n")

    for src_file, ttm_file in file_pairs:
        print(f"Processing {src_file} -> {ttm_file}")

        # Check if files exist
        if not os.path.exists(src_file):
            print(f"Error: Source file '{src_file}' not found", file=sys.stderr)
            continue
        if not args.dry_run and not os.path.exists(ttm_file):
            print(f"Error: TTM file '{ttm_file}' not found", file=sys.stderr)
            continue

        snippets = parse_file(src_file)
        total_snippets += len(snippets)

        if args.dry_run:
            print(f"Found {len(snippets)} snippets in {src_file}:")
            # Read file lines for debug output
            try:
                with open(src_file, "r", encoding="utf-8") as f:
                    lines = [line.rstrip("\n\r") for line in f.readlines()]

                for snippet in snippets:
                    print_snippet_debug(snippet, src_file, lines)
            except Exception as e:
                print(f"Error reading file for debug: {e}", file=sys.stderr)
        else:
            print(f"Found {len(snippets)} snippets")
            # Add file header to the combined content
            if snippets:
                all_macro_content.append(f"% Macros from {src_file}\n")

            for snippet in snippets:
                macro_output = run_katla_command(
                    snippet, src_file, ttm_file, args.dry_run
                )
                if macro_output and not macro_output.startswith("% Error"):
                    all_macro_content.append(macro_output)
                    if not macro_output.endswith("\n"):
                        all_macro_content.append("\n")
                    total_success += 1
                elif macro_output:
                    all_macro_content.append(macro_output)

            if snippets:
                all_macro_content.append("\n")

    # Write all macros to a single file
    if not args.dry_run:
        output_file = Path(args.output_dir) / "katla-macros.tex"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(output_file, "w") as f:
                f.writelines(all_macro_content)
            print(f"\nGenerated combined macro file: {output_file}")
        except Exception as e:
            print(f"Error writing combined macro file: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"Processed {total_success}/{total_snippets} snippets successfully")
        if total_success < total_snippets:
            sys.exit(1)
    else:
        # In dry run, still show what would be in the combined file
        print(
            f"\nWould generate combined macro file with {len(all_macro_content)} lines"
        )


if __name__ == "__main__":
    main()
