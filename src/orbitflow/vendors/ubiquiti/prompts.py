"""Structural EdgeSwitch exec prompts; annotations are not hostname facts."""
import re


def extract_edgeswitch_hostname(prompt: str) -> str:
    text = prompt.strip()
    simple = re.fullmatch(r"([^:#>\s()]+)[#>]", text)
    if simple:
        return simple[1]
    outer = re.fullmatch(r"\(([^:#>\s()]+)(.*?)\)[ \t]*[#>]", text)
    if outer:
        annotation = outer[2]
        if not annotation:
            return outer[1]
        if annotation[0] in " \t":
            annotation = annotation.strip(" \t")
            depth = 0
            if annotation.startswith("(") and annotation.endswith(")"):
                for index, character in enumerate(annotation):
                    if character in "\r\n":
                        break
                    depth += (character == "(") - (character == ")")
                    if depth <= 0 and index != len(annotation) - 1:
                        break
                else:
                    if depth == 0:
                        return outer[1]
    raise ValueError("unrecognized EdgeSwitch prompt")
