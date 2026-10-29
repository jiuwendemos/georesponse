import { jsPDF } from 'jspdf'
import type { Assessment, ReviewStatus, Scenario } from '../types'
import type { RankedSite } from './ranking'
import { downloadBlob, downloadText, euro, pct } from './format'

function savePdf(doc: jsPDF, filename: string): void {
  const blob = doc.output('blob')
  downloadBlob(blob, filename)
}

function header(doc: jsPDF, scenario: Scenario, title: string): number {
  const width = doc.internal.pageSize.getWidth()
  doc.setFillColor(8, 26, 36)
  doc.rect(0, 0, width, 34, 'F')
  doc.setTextColor(255, 255, 255)
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(17)
  doc.text('GeoResponse', 14, 15)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(8)
  doc.setTextColor(143, 216, 230)
  doc.text('AI analyst for imagery · human-signed assessment', 14, 22)
  doc.setTextColor(255, 255, 255)
  doc.setFontSize(11)
  doc.text(title, 14, 30)
  doc.setFontSize(7.5)
  doc.setTextColor(190, 205, 210)
  doc.text(`${scenario.meta.region} · ${scenario.meta.eventDate} · ${scenario.meta.areaKm2} km²`, width - 14, 30, { align: 'right' })
  doc.setTextColor(24, 35, 44)
  return 42
}

export function addMapImage(doc: jsPDF, dataUrl: string | null): void {
  if (!dataUrl) return
  const width = doc.internal.pageSize.getWidth()
  try {
    doc.addImage(dataUrl, 'PNG', 14, doc.internal.pageSize.getHeight() - 92, width - 28, 76)
  } catch {
    // map capture can fail on some GPU paths; the PDF still stands
  }
}

export function exportAssessmentPdf(
  scenario: Scenario,
  assessment: Assessment,
  ranked: RankedSite[],
  reviews: Record<string, ReviewStatus>,
  notes: Record<string, string>,
  mapImage: string | null,
): void {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  let y = header(doc, scenario, 'Assessment')
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(10)
  doc.text('Situation', 14, y)
  y += 5
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(8.6)
  doc.text(doc.splitTextToSize(assessment.summary, 180), 14, y)
  y += Math.max(14, doc.splitTextToSize(assessment.summary, 180).length * 4.2)

  doc.setFont('helvetica', 'bold')
  doc.setFontSize(10)
  doc.text('Ranked findings', 14, y)
  y += 6
  for (const item of ranked.slice(0, 9)) {
    if (y > 235) break
    const review = reviews[item.site.id] ?? 'pending'
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(8.4)
    doc.text(`${item.rank}. ${item.site.name}`, 14, y)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(7.4)
    doc.text(
      `${item.site.id} · ${item.site.severity} · ${pct(item.site.confidence)} · ${item.site.changeExtentM2.toLocaleString()} m² · ${euro(item.site.valueEur)} · ${item.site.accessStatus} · ${review}`,
      14,
      y + 4,
    )
    if (notes[item.site.id]) {
      doc.setTextColor(90, 100, 110)
      doc.text(doc.splitTextToSize(`Analyst note: ${notes[item.site.id]}`, 176), 14, y + 8)
      doc.setTextColor(24, 35, 44)
      y += 4
    }
    y += 11
  }

  doc.setFontSize(7.2)
  doc.setTextColor(90, 100, 110)
  doc.text(`Model ${assessment.modelVersion} · Imagery: ${scenario.meta.imagery.source} · Simulated demo pack`, 14, 282)
  doc.text('Human review required. Do not act on model output alone. © OpenStreetMap contributors (ODbL).', 14, 287)
  doc.setTextColor(24, 35, 44)
  addMapImage(doc, mapImage)
  savePdf(doc, `georesponse-assessment-${scenario.meta.id}.pdf`)
}

export function exportFieldOrderPdf(
  scenario: Scenario,
  assessment: Assessment,
  assignments: Record<string, string>,
  mapImage: string | null,
): void {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  let y = header(doc, scenario, 'Field order')
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(10)
  doc.text('Assignments', 14, y)
  y += 6
  const teams = Object.entries(assignments).sort(([a], [b]) => a.localeCompare(b))
  if (!teams.length) {
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(9)
    doc.text('No teams assigned.', 14, y)
    y += 8
  }
  for (const [siteId, team] of teams) {
    const site = scenario.sites.find((s) => s.id === siteId)
    if (!site) continue
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(9)
    doc.text(team, 14, y)
    doc.setFont('helvetica', 'normal')
    doc.text(`${site.name} (${site.id}) · ${site.severity} · ${site.accessStatus} access · ${site.responseMinutes} min`, 46, y)
    y += 7
  }
  y += 2
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(10)
  doc.text('Assessment', 14, y)
  y += 5
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(8.6)
  doc.text(doc.splitTextToSize(assessment.summary, 180), 14, y)
  y += 18
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(9)
  doc.text('Unassigned watch list', 14, y)
  y += 5
  doc.setFont('helvetica', 'normal')
  const watch = scenario.sites
    .filter((s) => !assignments[s.id])
    .sort((a, b) => b.rankScore - a.rankScore)
    .slice(0, 8)
    .map((s) => `${s.id} ${s.name} (${pct(s.confidence)})`)
    .join(' · ')
  doc.setFontSize(7.6)
  doc.text(doc.splitTextToSize(watch, 180), 14, y)
  addMapImage(doc, mapImage)
  doc.setFontSize(7)
  doc.setTextColor(90, 100, 110)
  doc.text(`Issued ${scenario.meta.eventDate} ${scenario.meta.eventTime} · Model ${assessment.modelVersion} · ${assessment.analyst}`, 14, 282)
  doc.text(`"${scenario.hero.quote}"`, 14, 287)
  savePdf(doc, `field-order-${scenario.meta.id}.pdf`)
}

export function exportGeoJson(
  scenario: Scenario,
  reviews: Record<string, ReviewStatus>,
  notes: Record<string, string>,
  assignments: Record<string, string>,
): void {
  const findings = {
    type: 'FeatureCollection',
    name: `${scenario.meta.id}-findings`,
    features: scenario.sites.map((site) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [site.lon, site.lat] },
      properties: {
        id: site.id,
        name: site.name,
        severity: site.severity,
        confidence: site.confidence,
        changeExtentM2: site.changeExtentM2,
        valueEur: site.valueEur,
        population: site.population,
        access: site.accessStatus,
        review: reviews[site.id] ?? 'pending',
        note: notes[site.id] ?? '',
        team: assignments[site.id] ?? null,
        modelVersion: scenario.meta.model,
        imagery: scenario.meta.imagery.source,
        simulated: scenario.meta.imagery.simulated,
      },
    })),
  }
  downloadText(JSON.stringify(findings, null, 2), `georesponse-${scenario.meta.id}-findings.geojson`, 'application/geo+json')

  const overlay = {
    type: 'FeatureCollection',
    name: `${scenario.meta.id}-change-overlay`,
    features: scenario.timeline.frames.map((frame) => ({
      type: 'Feature',
      geometry: frame.geometry,
      properties: { t: frame.t, label: frame.label, areaKm2: frame.areaKm2 },
    })),
  }
  downloadText(JSON.stringify(overlay, null, 2), `georesponse-${scenario.meta.id}-change-overlay.geojson`, 'application/geo+json')
}

export function exportAssessmentJson(
  scenario: Scenario,
  assessment: Assessment,
  reviews: Record<string, ReviewStatus>,
  notes: Record<string, string>,
  assignments: Record<string, string>,
): void {
  const payload = {
    scenario: scenario.meta.id,
    generatedAt: new Date().toISOString(),
    assessment,
    reviews,
    notes,
    assignments,
    provenance: scenario.provenance,
  }
  downloadText(JSON.stringify(payload, null, 2), `georesponse-${scenario.meta.id}-assessment.json`, 'application/json')
}
