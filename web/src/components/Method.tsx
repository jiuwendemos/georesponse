import { useEffect, useState } from 'react'
import { useApp } from '../store'
import { asset, dataPath, loadJson } from '../lib/data'
import type { PrivacyData } from '../types'
import { Icon } from './ui'
import { pct } from '../lib/format'

interface Integrations {
  claims: string[]
  gis: string[]
  field: string[]
  imagery: string[]
  note: string
  policies: { autoApprove: boolean; humanInTheLoop: boolean; template: string }
}

interface Npu {
  device: string
  batchSize: number
  tilesPerMinute: number
  models: { name: string; version: string; pinned: boolean }[]
  note: string
}

interface ModelCard {
  model: string
  task: string
  trainedRows: number
  metrics: { precision: number; recall: number; f1: number; rows: number }
  weights: number[]
  limitations: string[]
}

interface SectorPack {
  id: string
  title: string
  buyers: string[]
  changeTypes: string[]
  firstWorkflow: string
  guardrails: string[]
}

interface PackData {
  packs: SectorPack[]
  partner: { title: string; partners: string[]; terms: string }
  government: { title: string; scope: string; obligations: string[] }
}

const PIPELINE = [
  { n: '01', title: 'Imagery arrives', body: 'Sentinel-2, commercial, or customer drone orthophoto. Tiled and projection-normalised.' },
  { n: '02', title: 'Change is detected', body: 'Paired tiles, cloud screen, change map, severity band. Precomputed for the stage, real for the pilot.' },
  { n: '03', title: 'Context is added', body: 'Roads, buildings, power, population and insured value. A changed roof becomes policy XYZ.' },
  { n: '04', title: 'What matters is ranked', body: 'Extent, confidence, value at risk, access and people. Every contribution is visible.' },
  { n: '05', title: 'An analyst checks', body: 'Approve, flag or reject. A rejection removes the finding and re-orders the list in the same scene.' },
  { n: '06', title: 'Map and report are ready', body: 'Assessment, field order and GeoJSON, signed by a human with an audit trail.' },
]

export default function Method() {
  const app = useApp()
  const scenario = app.scenario
  const [privacy, setPrivacy] = useState<PrivacyData | null>(null)
  const [integrations, setIntegrations] = useState<Integrations | null>(null)
  const [npu, setNpu] = useState<Npu | null>(null)
  const [modelCard, setModelCard] = useState<ModelCard | null>(null)
  const [packData, setPackData] = useState<PackData | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      loadJson<PrivacyData>(dataPath('privacy.json')),
      loadJson<Integrations>(dataPath('integrations.json')),
      loadJson<Npu>(dataPath('npu.json')),
      loadJson<ModelCard>(dataPath('model-card.json')),
      loadJson<PackData>(dataPath('packs.json')),
    ])
      .then(([privacyData, integrationsData, npuData, modelData, packInfo]) => {
        if (!alive) return
        setPrivacy(privacyData)
        setIntegrations(integrationsData)
        setNpu(npuData)
        setModelCard(modelData)
        setPackData(packInfo)
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])

  if (!scenario) return null

  return (
    <div className="page method">
      <header className="page-head">
        <div>
          <div className="eyebrow">
            <span className="dot" /> Method & provenance
          </div>
          <h1>Not a black box. A pipeline with a signature.</h1>
          <p>
            GeoResponse is an analyst, not an oracle. Every number on the map has an imagery source, a model version and a
            human decision behind it. This page is the provenance sheet the booth asks for.
          </p>
        </div>
        <div className="page-head-actions">
          <button className="btn" onClick={() => app.openProvenance(true)}>
            <Icon name="shield" size={14} /> Provenance panel
          </button>
          <button className="btn btn-primary" onClick={() => void app.saveOffline()}>
            <Icon name="download" size={14} /> Save offline pack
          </button>
        </div>
      </header>

      <section className="pipeline">
        {PIPELINE.map((step, index) => (
          <div className="pipeline-step" key={step.n}>
            <span className="pipeline-n">{step.n}</span>
            <b>{step.title}</b>
            <p>{step.body}</p>
            {index < PIPELINE.length - 1 && <span className="pipeline-arrow"><Icon name="arrow" size={14} /></span>}
          </div>
        ))}
      </section>

      <section className="card imagery-pair-card">
        <div className="card-head">
          <div>
            <span className="eyebrow">Imagery pair</span>
            <h2>Before / after, cached locally</h2>
          </div>
          <span className="card-tag">simulated · attribution on screen</span>
        </div>
        <div className="imagery-pair">
          <figure>
            <img src={asset(scenario.imageryPair.before)} alt="Before imagery" loading="lazy" />
            <figcaption>Before · {scenario.meta.imagery.acquired}</figcaption>
          </figure>
          <figure>
            <img src={asset(scenario.imageryPair.after)} alt="After imagery with change extent" loading="lazy" />
            <figcaption>After · change extent overlay</figcaption>
          </figure>
        </div>
        <p className="card-note">{scenario.imageryPair.caption}</p>
      </section>

      <section className="method-grid">
        <div className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Model card</span>
              <h2>{scenario.meta.model}</h2>
            </div>
            <span className="card-tag">pinned on every assessment</span>
          </div>
          <dl className="definition">
            <dt>Task</dt>
            <dd>Change and damage detection on paired 10 m imagery tiles; severity classification.</dd>
            <dt>Imagery</dt>
            <dd>{scenario.meta.imagery.source} · {scenario.meta.imagery.resolution} · acquired {scenario.meta.imagery.acquired}</dd>
            <dt>Cloud screen</dt>
            <dd>Exclude tiles above 30% cloud. Sentinel scene classification preferred in production.</dd>
            <dt>Ranking weights</dt>
            <dd>
              {Object.entries(scenario.meta.weights).map(([key, value]) => (
                <span className="weight" key={key}>
                  {key} <b>{pct(value)}</b>
                </span>
              ))}
            </dd>
            <dt>Human review</dt>
            <dd>Mandatory. No automated decision about people or property. Every rejection keeps its reason.</dd>
            <dt>Fit</dt>
            <dd>
              {modelCard
                ? `${modelCard.trainedRows} synthetic rows · precision ${pct(modelCard.metrics.precision)} · recall ${pct(modelCard.metrics.recall)} · F1 ${modelCard.metrics.f1}`
                : 'loading the pinned model card…'}
            </dd>
            <dt>Limitations</dt>
            <dd>Dark roofs, wet pavement and shadow can mimic damage. Confidence is not truth; the analyst signs.</dd>
          </dl>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Data rights</span>
              <h2>Cleared for the demo?</h2>
            </div>
          </div>
          <ul className="rights-list">
            {scenario.provenance.dataRights.map((right) => (
              <li key={right}>
                <Icon name="check" size={13} /> {right}
              </li>
            ))}
          </ul>
          <div className="provenance-box">
            <span className="eyebrow">Bundled pack</span>
            <b>{scenario.meta.imagery.simulated ? 'Simulated imagery — clearly labelled' : 'Customer imagery — licensed'}</b>
            <p>{scenario.provenance.imagery.notes}</p>
            <p>{scenario.meta.imagery.attribution}</p>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Imagery connectors</span>
              <h2>Bring your own pixels</h2>
            </div>
          </div>
          <div className="tag-cloud">
            {integrations?.imagery.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
          <p className="card-note">
            {integrations?.note ?? 'All connectors share one interface: list, fetch, health. Network connectors are dry-run by default.'}
          </p>
          <div className="connector-state">
            <span className="live-dot" /> offline demo pack · live connectors configurable
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">System integrations</span>
              <h2>Fits the customer workflow</h2>
            </div>
          </div>
          <div className="integration-cols">
            <div>
              <span>Claims</span>
              {integrations?.claims.map((item) => <b key={item}>{item}</b>)}
            </div>
            <div>
              <span>GIS</span>
              {integrations?.gis.map((item) => <b key={item}>{item}</b>)}
            </div>
            <div>
              <span>Field</span>
              {integrations?.field.map((item) => <b key={item}>{item}</b>)}
            </div>
          </div>
          <p className="card-note">
            Adapters are pure transforms. Claims are created as drafts requiring an adjuster. {integrations?.policies.humanInTheLoop ? 'Human in the loop.' : ''}{' '}
            {integrations?.policies.autoApprove ? 'Auto-approve enabled.' : 'Auto-approve disabled.'}
          </p>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Deployment</span>
              <h2>On-site, offline, optional NPU</h2>
            </div>
          </div>
          <dl className="definition">
            <dt>Targets</dt>
            <dd>Linux · Docker · private cloud · edge NPU</dd>
            <dt>Network</dt>
            <dd>No outbound network after imagery delivery. The stage pack is fully local.</dd>
            <dt>NPU profile</dt>
            <dd>{npu?.device ?? 'Ascend 310P'} · batch {npu?.batchSize ?? 8} · {npu?.tilesPerMinute ?? 2140} tiles/min</dd>
            <dt>Models</dt>
            <dd>{npu?.models.map((model) => `${model.name} ${model.version} (pinned)`).join(' · ') ?? scenario.meta.model}</dd>
            <dt>Sovereignty</dt>
            <dd>Imagery and compute stay inside the customer network.</dd>
          </dl>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Privacy review</span>
              <h2>Residential imagery</h2>
            </div>
            <span className="card-tag">{privacy ? `${privacy.done}/${privacy.done + privacy.open}` : '—'}</span>
          </div>
          <div className="checklist">
            {privacy?.items.map((item) => (
              <div className={item.status === 'done' ? 'check done' : 'check'} key={item.id}>
                <span>{item.status === 'done' ? <Icon name="check" size={12} /> : ''}</span>
                <p>{item.requirement}</p>
              </div>
            ))}
          </div>
          <p className="card-note">{privacy?.note}</p>
        </div>
      </section>

      <section className="card sector-card">
        <div className="card-head">
          <div>
            <span className="eyebrow">Beyond the first pilot</span>
            <h2>Sector packs & partner motion</h2>
          </div>
          <span className="card-tag">same engine, different context</span>
        </div>
        <div className="sector-grid">
          {packData?.packs.map((pack) => (
            <div className="sector" key={pack.id}>
              <b>{pack.title}</b>
              <p>{pack.firstWorkflow}</p>
              <div className="tag-cloud">
                {pack.changeTypes.slice(0, 3).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
              <small>{pack.guardrails[0]}</small>
            </div>
          ))}
          <div className="sector">
            <b>{packData?.government.title ?? 'Government framework'}</b>
            <p>{packData?.government.scope}</p>
            <div className="tag-cloud">
              {packData?.government.obligations.slice(0, 3).map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
            <small>{packData?.partner.terms}</small>
          </div>
        </div>
      </section>

      <section className="card reproduce">
        <div className="card-head">
          <div>
            <span className="eyebrow">Reproduce</span>
            <h2>Every number on this page is generated</h2>
          </div>
        </div>
        <pre>
          <code>{`py -m georesponse.datapack          # build the offline demo packs
py -m pytest                        # ranking, detection, exports, audit
cd web && npm run build             # static app, no CDN
py -m georesponse.cli serve         # optional pilot API`}</code>
        </pre>
        <p className="card-note">
          The demo pack is deterministic. The same seed builds the same flood, the same false positive and the same 42 minutes.
          Replace the pack with licensed imagery and adjuster-confirmed labels for a pilot.
        </p>
      </section>

      <footer className="page-foot">
        <span>GeoResponse · Apache-2.0 · {scenario.meta.disclaimer}</span>
        <span>{scenario.meta.imagery.attribution} · © OpenStreetMap contributors (ODbL)</span>
      </footer>
    </div>
  )
}
