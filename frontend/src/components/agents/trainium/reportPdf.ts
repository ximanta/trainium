import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

import type { Report, Score } from "@/components/agents/trainium/reportTypes";

/** Palette kept in RGB triples because jsPDF takes no hex. Mirrors the on-screen
 *  report so a printed copy reads as the same document. */
const INK: [number, number, number] = [24, 27, 34];
const MUTED: [number, number, number] = [117, 126, 141];
const ACCENT: [number, number, number] = [67, 56, 202];
const GOOD: [number, number, number] = [21, 112, 63];
const WARN: [number, number, number] = [162, 87, 10];
const LINE: [number, number, number] = [231, 228, 223];

const MARGIN = 18;

function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Draw the score profile as vectors.
 *
 *  jsPDF draws rather than screenshots, so the on-screen SVG cannot be
 *  reused: the same geometry is computed again here. Vector rather than a
 *  rasterised canvas, so it stays sharp when printed and adds almost nothing
 *  to the file size.
 *
 *  Returns the y position below the chart.
 */
function radar(
  pdf: jsPDF,
  scores: Score[],
  cx: number,
  cy: number,
  radius: number
): number {
  const n = scores.length;
  // Under three axes a polygon degenerates to a line or a point.
  if (n < 3) return cy;

  const at = (i: number, value: number, r = radius) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    const d = (r * value) / 5;
    return { x: cx + d * Math.cos(angle), y: cy + d * Math.sin(angle) };
  };

  pdf.setDrawColor(...LINE);
  pdf.setLineWidth(0.2);
  for (let ring = 1; ring <= 5; ring++) {
    pdf.circle(cx, cy, (radius * ring) / 5, "S");
  }
  for (let i = 0; i < n; i++) {
    const end = at(i, 5);
    pdf.line(cx, cy, end.x, end.y);
  }

  // lines() takes deltas from a start point, not absolute coordinates.
  const points = scores.map((s, i) => at(i, s.score));
  const deltas: [number, number][] = [];
  for (let i = 1; i < points.length; i++) {
    deltas.push([points[i].x - points[i - 1].x, points[i].y - points[i - 1].y]);
  }
  deltas.push([points[0].x - points[n - 1].x, points[0].y - points[n - 1].y]);

  pdf.setFillColor(224, 222, 250);
  pdf.setDrawColor(...ACCENT);
  pdf.setLineWidth(0.5);
  pdf.lines(deltas, points[0].x, points[0].y, [1, 1], "FD");

  pdf.setFillColor(...ACCENT);
  for (const p of points) pdf.circle(p.x, p.y, 0.8, "F");

  pdf.setFontSize(6);
  pdf.setTextColor(...MUTED);
  for (let i = 0; i < n; i++) {
    const label = at(i, 5, radius + 7);
    const word = scores[i].label.split(/\s+/)[0];
    pdf.text(word, label.x, label.y + (label.y < cy ? -0.5 : 2), { align: "center" });
  }

  return cy + radius + 12;
}

/** Draws the Trainium wordmark. Set as vector text rather than an image so it
 *  stays crisp at any zoom and adds nothing to the file size. */
function wordmark(pdf: jsPDF, x: number, y: number) {
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(15);
  pdf.setTextColor(...INK);
  pdf.text("trainium", x, y);
  const w = pdf.getTextWidth("trainium");
  pdf.setTextColor(16, 185, 129);
  pdf.text(".", x + w, y);
}

export function downloadReportPdf(
  report: Report,
  meta: {
    title: string;
    trainerName: string;
    durationMin: number;
    learners: number;
    date: string;
  }
) {
  const pdf = new jsPDF({ unit: "mm", format: "a4" });
  const pageW = pdf.internal.pageSize.getWidth();
  const contentW = pageW - MARGIN * 2;
  let y = MARGIN;

  // ---- page 1 masthead -------------------------------------------------
  wordmark(pdf, MARGIN, y + 2);

  pdf.setFont("helvetica", "normal");
  pdf.setFontSize(7.5);
  pdf.setTextColor(...MUTED);
  pdf.text("SESSION REPORT", pageW - MARGIN, y, { align: "right" });
  pdf.text(meta.date, pageW - MARGIN, y + 4.5, { align: "right" });

  y += 9;
  pdf.setDrawColor(...LINE);
  pdf.setLineWidth(0.3);
  pdf.line(MARGIN, y, pageW - MARGIN, y);

  y += 11;
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(18);
  pdf.setTextColor(...INK);
  pdf.text(meta.title || "Session report", MARGIN, y);

  y += 7;
  pdf.setFont("helvetica", "normal");
  pdf.setFontSize(9);
  pdf.setTextColor(...MUTED);
  const facts = [
    meta.trainerName,
    `${meta.durationMin} min`,
    `${meta.learners} learner${meta.learners === 1 ? "" : "s"}`,
  ].filter(Boolean);
  pdf.text(facts.join("   ·   "), MARGIN, y);

  // ---- verdict ---------------------------------------------------------
  if (report.summary) {
    y += 10;
    pdf.setFontSize(10.5);
    pdf.setTextColor(...INK);
    const lines = pdf.splitTextToSize(report.summary, contentW);
    pdf.text(lines, MARGIN, y);
    y += lines.length * 5.2;
  }

  // ---- coverage, measured rather than scored ---------------------------
  if (report.coverage && report.coverage.slides_total > 0) {
    const c = report.coverage;
    y += 7;
    pdf.setFontSize(8);
    pdf.setTextColor(...MUTED);
    pdf.text(
      `Material covered: ${Math.round(c.fraction * 100)}% (reached slide ` +
        `${c.furthest_slide} of ${c.slides_total})     ` +
        `Time used: ${Math.round(c.elapsed_min)} of ${c.planned_min} min`,
      MARGIN,
      y
    );
    y += 2;
  }

  // ---- profile, highest scoring first ----------------------------------
  const assessed = [...(report.scores ?? []), ...(report.video_scores ?? [])];
  const ranked = [...assessed].sort((a, b) => b.score - a.score);
  if (ranked.length >= 3) {
    // Centred on the right so the chart and the table below it do not fight
    // for the same column.
    const after = radar(pdf, ranked, pageW - MARGIN - 32, y + 34, 26);
    y = after;
  }

  // ---- scores at a glance ---------------------------------------------
  if (assessed.length) {
    y += 8;
    autoTable(pdf, {
      startY: y,
      head: [["Criterion", "Score", "Why"]],
      body: assessed.map((s) => [s.label, `${s.score}/5`, s.rationale]),
      theme: "plain",
      margin: { left: MARGIN, right: MARGIN },
      headStyles: {
        fontSize: 8,
        fontStyle: "bold",
        textColor: MUTED,
        lineWidth: { bottom: 0.3 },
        lineColor: LINE,
      },
      bodyStyles: { fontSize: 8.5, textColor: INK, cellPadding: { top: 2.6, bottom: 2.6 } },
      columnStyles: {
        0: { cellWidth: 42, fontStyle: "bold" },
        1: { cellWidth: 14, halign: "center" },
        2: { textColor: MUTED },
      },
      // Colour the score, so a 2 reads as a 2 without reading the sentence.
      didParseCell: (data) => {
        if (data.section === "body" && data.column.index === 1) {
          const n = Number(String(data.cell.raw).split("/")[0]);
          data.cell.styles.textColor = n <= 2 ? WARN : n >= 4 ? GOOD : INK;
          data.cell.styles.fontStyle = "bold";
        }
      },
    });
    y = (pdf as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY;
  }

  // ---- takeaways -------------------------------------------------------
  const bullets = (
    heading: string,
    items: string[],
    colour: [number, number, number]
  ) => {
    if (!items.length) return;
    if (y > 250) {
      pdf.addPage();
      y = MARGIN;
    }
    y += 9;
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(9);
    pdf.setTextColor(...colour);
    pdf.text(heading.toUpperCase(), MARGIN, y);
    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(9);
    pdf.setTextColor(...INK);
    for (const item of items) {
      y += 5.4;
      const lines = pdf.splitTextToSize(item, contentW - 5);
      if (y + lines.length * 4.4 > 280) {
        pdf.addPage();
        y = MARGIN;
      }
      pdf.setTextColor(...colour);
      pdf.text("•", MARGIN, y);
      pdf.setTextColor(...INK);
      pdf.text(lines, MARGIN + 4, y);
      y += (lines.length - 1) * 4.4;
    }
  };

  bullets("What worked", report.strengths ?? [], GOOD);
  bullets("What to work on", report.improvements ?? [], WARN);

  // ---- evidence, one section per rubric --------------------------------
  const evidenceSection = (heading: string, scores: Score[], from: string) => {
    if (!scores.length) return;
    pdf.addPage();
    y = MARGIN;
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(12);
    pdf.setTextColor(...INK);
    pdf.text(heading, MARGIN, y);
    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(8);
    pdf.setTextColor(...MUTED);
    pdf.text(from, pageW - MARGIN, y, { align: "right" });
    y += 3;
    pdf.setDrawColor(...LINE);
    pdf.line(MARGIN, y, pageW - MARGIN, y);
    y += 8;

    for (const s of scores) {
      const rationale = pdf.splitTextToSize(s.rationale, contentW);
      const needed = 10 + rationale.length * 4.2 + s.evidence.length * 9;
      if (y + needed > 280) {
        pdf.addPage();
        y = MARGIN;
      }

      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(10);
      pdf.setTextColor(...INK);
      pdf.text(s.label, MARGIN, y);
      const tone = s.score <= 2 ? WARN : s.score >= 4 ? GOOD : ACCENT;
      pdf.setTextColor(...tone);
      pdf.text(`${s.score}/5`, pageW - MARGIN, y, { align: "right" });

      // Score bar: the same visual weight the reader saw on screen.
      y += 2.4;
      pdf.setFillColor(234, 231, 226);
      pdf.rect(MARGIN, y, contentW, 1.1, "F");
      pdf.setFillColor(...tone);
      pdf.rect(MARGIN, y, (contentW * s.score) / 5, 1.1, "F");

      y += 5.5;
      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(9);
      pdf.setTextColor(...MUTED);
      pdf.text(rationale, MARGIN, y);
      y += rationale.length * 4.2;

      for (const e of s.evidence) {
        const quote = e.source === "video" ? e.quote : `"${e.quote}"`;
        const lines = pdf.splitTextToSize(quote, contentW - 16);
        if (y + lines.length * 4 > 282) {
          pdf.addPage();
          y = MARGIN;
        }
        y += 4;
        pdf.setDrawColor(...(e.positive ? GOOD : WARN));
        pdf.setLineWidth(0.6);
        pdf.line(MARGIN + 1, y - 3, MARGIN + 1, y + (lines.length - 1) * 4 + 1);
        pdf.setLineWidth(0.3);
        pdf.setFontSize(8);
        pdf.setTextColor(...MUTED);
        pdf.text(clock(e.ts_start), MARGIN + 4, y);
        pdf.setTextColor(...INK);
        pdf.text(lines, MARGIN + 16, y);
        y += (lines.length - 1) * 4 + 1;
      }
      y += 8;
    }
  };

  evidenceSection("How you taught", report.scores ?? [], "from the transcript");
  evidenceSection("How you came across", report.video_scores ?? [], "from the recording");

  // ---- not assessed ----------------------------------------------------
  const skipped = report.undetermined ?? [];
  if (skipped.length) {
    if (y > 235) {
      pdf.addPage();
      y = MARGIN;
    }
    y += 4;
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(9);
    pdf.setTextColor(...MUTED);
    pdf.text("NOT ASSESSED IN THIS SESSION", MARGIN, y);
    y += 2;
    autoTable(pdf, {
      startY: y,
      body: skipped.map((u) => [u.label, u.reason]),
      theme: "plain",
      margin: { left: MARGIN, right: MARGIN },
      bodyStyles: { fontSize: 8, textColor: MUTED, cellPadding: { top: 1.8, bottom: 1.8 } },
      columnStyles: { 0: { cellWidth: 46, fontStyle: "bold" } },
    });
  }

  // ---- footers ---------------------------------------------------------
  const pages = pdf.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    pdf.setPage(i);
    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(7.5);
    pdf.setTextColor(...MUTED);
    pdf.text(
      "Every score cites the moment it came from.",
      MARGIN,
      pdf.internal.pageSize.getHeight() - 10
    );
    pdf.text(
      `${i} / ${pages}`,
      pageW - MARGIN,
      pdf.internal.pageSize.getHeight() - 10,
      { align: "right" }
    );
  }

  const slug = (meta.title || "session").toLowerCase().replace(/[^a-z0-9]+/g, "-");
  pdf.save(`trainium-${slug}-${meta.date.replace(/\s+/g, "-")}.pdf`);
}
