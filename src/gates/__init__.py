"""Fail-closed preregistration gates for KYRA-Bench.

`gates.freeze` freezes a preregistration YAML only after it parses, matches the
schema and agrees with the claim contract, writing the .sha256 receipt itself.
`gates.verify_freeze` is what confirmatory scripts call before they run.
"""
