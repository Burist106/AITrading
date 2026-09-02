export class UnexpectedConsoleGuard {
  readonly messages: string[] = [];

  capture(kind: "error" | "warning", values: unknown[]): void {
    const rendered = values
      .map((value) => (value instanceof Error ? value.message : String(value)))
      .join(" ");
    this.messages.push(`${kind}: ${rendered}`);
  }

  assertClean(): void {
    if (this.messages.length > 0) {
      throw new Error(
        `Unexpected console or rejection output:\n${this.messages.join("\n")}`,
      );
    }
  }
}
