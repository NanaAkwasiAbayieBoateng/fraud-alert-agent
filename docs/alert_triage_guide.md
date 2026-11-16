# Fraud Alert Triage Guide

Every alert gets the same first pass, in this order. The goal is evidence,
not speed: a triaged alert should let a second analyst reach the same
conclusion from the file alone.

## Step 1 — Confirm the alert facts

Check the flagged transaction itself: amount, merchant, timestamp, and the
rule that fired. Note anything that does not match the rule (a "velocity"
alert with a single transaction is usually a data problem, not fraud).

## Step 2 — Compare against the account's own baseline

Pull the account's statistics: transaction count, average and maximum
amounts, usual merchants, and how long the account has been open. Judge
the flagged transaction against this account's habits, not against a
global threshold. A $600 purchase is routine for one customer and a
five-alarm outlier for another.

## Step 3 — Look for a pattern around the alert

Review at least the surrounding 72 hours. Small, round-amount charges
from an unfamiliar merchant shortly before a large charge are a classic
card-testing pattern and raise the severity. A single isolated anomaly
with an otherwise clean history usually lowers it.

## Step 4 — Check the relevant policy

Match the alert type to the specific review policy (high-value purchases,
velocity bursts, geographic mismatches) and note which policy points the
evidence satisfies.

## Step 5 — Draft, don't decide

The investigator drafts a case summary with the evidence and a
recommended disposition. Filing, blocking, or clearing always requires a
human approval. Record what you could not verify — gaps are findings too.
