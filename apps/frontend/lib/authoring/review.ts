export type ReviewDecision = "accept" | "edit" | "discard";

export type ProposedOperation = {
  id: string;
  operation: "create" | "revise" | "deprecate";
  document_type: string;
  document: string;
  justification: string;
  depends_on: string[];
  evidence: { field: string; source: string }[];
  gaps: { capability: string; reason: string; status?: string }[];
  decision: "pending" | ReviewDecision;
};

export function reviewedOperations(
  operations: ProposedOperation[],
  decisions: Record<string, ReviewDecision>,
  documents: Record<string, string>,
) {
  const discarded = new Set(
    operations.filter((operation) => decisions[operation.id] === "discard").map((operation) => operation.id),
  );
  let changed = true;
  while (changed) {
    changed = false;
    for (const operation of operations) {
      if (!discarded.has(operation.id) && operation.depends_on.some((dependency) => discarded.has(dependency))) {
        discarded.add(operation.id);
        changed = true;
      }
    }
  }
  return operations
    .filter((operation) => !discarded.has(operation.id))
    .map((operation) => ({
      ...operation,
      document: documents[operation.id] ?? operation.document,
      decision: decisions[operation.id] ?? "pending",
    }));
}