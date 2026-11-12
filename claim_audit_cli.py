"""Console launcher for the digit-prefixed package."""
from importlib import import_module

main = import_module("3d_reconstruction_claim_audit.audit").main
