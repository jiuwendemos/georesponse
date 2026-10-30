import { describe, expect, it } from 'vitest'
import { parseCsv, parseGeoJson, toCsv, toGeoJson } from './workspace'

describe('workspace import', () => {
  it('parses the example CSV contract', () => {
    const csv = 'id,name,lat,lon,severity,confidence,value_eur,population,access,notes\n' +
      'S-1,Care campus,50.545,7.100,red,0.91,"6,200,000",1800,flooded,Access flooded\n'
    const result = parseCsv(csv)
    expect(result.errors).toEqual([])
    expect(result.sites).toHaveLength(1)
    expect(result.sites[0]).toMatchObject({
      id: 'S-1',
      name: 'Care campus',
      lat: 50.545,
      lon: 7.1,
      severity: 'red',
      confidence: 0.91,
      valueEur: 6200000,
      population: 1800,
      access: 'flooded',
    })
  })

  it('rejects rows without a valid coordinate', () => {
    const result = parseCsv('name,lat,lon\nBroken,200,7\nGood,50.5,7.1\n')
    expect(result.sites).toHaveLength(1)
    expect(result.errors[0]).toContain('lat must be between')
  })

  it('accepts GeoJSON points and skips other geometries', () => {
    const geojson = JSON.stringify({
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', id: 'P-1', geometry: { type: 'Point', coordinates: [7.1, 50.5] }, properties: { name: 'Pump', severity: 'orange', value_eur: 1200 } },
        { type: 'Feature', geometry: { type: 'LineString', coordinates: [[7, 50], [7.1, 50.1]] }, properties: { name: 'Road' } },
      ],
    })
    const result = parseGeoJson(geojson)
    expect(result.sites).toHaveLength(1)
    expect(result.errors[0]).toContain('only Point geometries')
    expect(result.sites[0].severity).toBe('orange')
  })

  it('round-trips through CSV and GeoJSON', () => {
    const site = { id: 'S-1', name: 'Care campus', lat: 50.545, lon: 7.1, severity: 'red' as const, confidence: 0.9, valueEur: 10, population: 2, access: 'clear', notes: 'note' }
    expect(parseCsv(toCsv([site])).sites[0]).toMatchObject({ id: 'S-1', name: 'Care campus', severity: 'red' })
    expect(parseGeoJson(toGeoJson([site])).sites[0]).toMatchObject({ id: 'S-1', lon: 7.1, lat: 50.545 })
  })
})
