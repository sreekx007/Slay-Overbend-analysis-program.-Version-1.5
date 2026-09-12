"""slay.entry -- Case validation gate and command-line entry point.

The only place stages are sequenced. Refuses an under-specified case
rather than defaulting a physical quantity, and stamps every resolved
value with its provenance.

Workflow: thin sequencing only.
"""
