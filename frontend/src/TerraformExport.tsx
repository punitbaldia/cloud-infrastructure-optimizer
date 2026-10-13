import { useState } from 'react';
import { api } from './api';

export default function TerraformExport({ id }: { id: string }) {
  const [bundle, setBundle] = useState<any>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function prepare() {
    setBusy(true); setError('');
    try { setBundle(await api('/recommendations/' + id + '/terraform', 'POST')); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(bundle.files[bundle.filename], null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = bundle.filename; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="panel padded">
    <h3>Terraform workflow</h3>
    <p className="muted">Prepare a file for review and execution with Terraform. Exporting does not change AWS.</p>
    <button className="secondary" disabled={busy} onClick={prepare}>{busy ? 'Preparing…' : 'Prepare Terraform export'}</button>
    {error && <p role="alert" className="error">{error}</p>}
    {bundle && <><p>{bundle.simulated ? 'Demo export: no AWS actions.' : 'Live export: review before applying.'}</p>
      <ol>{bundle.instructions.map((step: string) => <li key={step}>{step}</li>)}</ol>
      <button className="secondary" onClick={download}>Download Terraform file</button></>}
  </div>;
}
