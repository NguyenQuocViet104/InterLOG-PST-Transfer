import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Archive, CalendarClock, CheckCircle2, ChevronRight, CircleAlert, Clock3,
  Database, HardDriveDownload, History, Inbox, LayoutDashboard, Plus,
  RefreshCw, Search, Server, ShieldCheck, X
} from 'lucide-react'
import './styles.css'

const API = import.meta.env.VITE_API_URL || ''
const scopeNames = { primary: 'Mailbox chính', online_archive: 'Online Archive', folder: 'Thư mục cụ thể' }
const statusNames = {
  SCHEDULED: 'Đã lên lịch', WAITING_AUTH: 'Chờ xác thực', EXPORTING: 'Đang export',
  PST_READY: 'PST sẵn sàng', TRANSFERRING: 'Đang chuyển', VERIFYING: 'Đang xác minh',
  COMPLETE: 'Hoàn tất', FAILED: 'Thất bại', CANCELLED: 'Đã hủy'
}

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}

function Status({ value }) {
  const tone = value === 'COMPLETE' ? 'success' : value === 'FAILED' ? 'danger' : value === 'CANCELLED' ? 'muted' : 'active'
  return <span className={`status ${tone}`}><i />{statusNames[value] || value}</span>
}

function NewJob({ onClose, onCreated }) {
  const local = new Date(Date.now() + 60000)
  local.setMinutes(local.getMinutes() - local.getTimezoneOffset())
  const [form, setForm] = useState({
    mailbox: '', scope: 'online_archive', folder_name: '', export_engine: 'purview',
    auth_mode: 'app_only', scheduled_at: local.toISOString().slice(0, 16),
    destination: 'D:\\MAIL BACKUP', note: ''
  })
  const [error, setError] = useState('')
  const submit = async (event) => {
    event.preventDefault(); setError('')
    const payload = { ...form, scheduled_at: new Date(form.scheduled_at).toISOString() }
    const response = await fetch(`${API}/api/jobs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    if (!response.ok) { const body = await response.json(); setError(body.detail || 'Không tạo được job'); return }
    onCreated(); onClose()
  }
  return <div className="modal-backdrop"><form className="modal" onSubmit={submit}>
    <div className="modal-head"><div><span className="eyebrow">YÊU CẦU MỚI</span><h2>Lên lịch backup mail</h2><p>Chỉ IT quản lý. Hệ thống không nhận hoặc lưu mật khẩu người dùng.</p></div><button type="button" className="icon-btn" onClick={onClose}><X /></button></div>
    <div className="form-grid">
      <label className="wide">Email người dùng<input required type="email" placeholder="user@company.com" value={form.mailbox} onChange={e => setForm({...form, mailbox:e.target.value})}/></label>
      <label>Phạm vi<select value={form.scope} onChange={e => setForm({...form, scope:e.target.value})}><option value="online_archive">Online Archive</option><option value="primary">Mailbox chính</option><option value="folder">Thư mục cụ thể</option></select></label>
      <label>Tên thư mục<input disabled={form.scope !== 'folder'} required={form.scope === 'folder'} placeholder="Ví dụ: Inbox/Projects" value={form.folder_name} onChange={e => setForm({...form, folder_name:e.target.value})}/></label>
      <label>Engine export<select value={form.export_engine} onChange={e => setForm({...form, export_engine:e.target.value, auth_mode:e.target.value==='purview'?'app_only':'interactive_oauth'})}><option value="purview">Purview eDiscovery (khuyên dùng)</option><option value="outlook_manual">Outlook Classic (fallback)</option></select></label>
      <label>Xác thực<select value={form.auth_mode} disabled={form.export_engine==='purview'} onChange={e => setForm({...form, auth_mode:e.target.value})}><option value="app_only">App-only / RBAC</option><option value="interactive_oauth">Đăng nhập OAuth tương tác</option></select></label>
      <label>Lịch chạy<input required type="datetime-local" value={form.scheduled_at} onChange={e => setForm({...form, scheduled_at:e.target.value})}/></label>
      <label>Thư mục PST đích<input required value={form.destination} onChange={e => setForm({...form, destination:e.target.value})}/></label>
      <label className="wide">Ghi chú<textarea rows="3" placeholder="Mã ticket, yêu cầu đặc biệt..." value={form.note} onChange={e => setForm({...form, note:e.target.value})}/></label>
    </div>
    <div className="security-note"><ShieldCheck/><div><strong>Không lưu password Microsoft 365</strong><span>App-only dùng certificate/RBAC. Fallback dùng OAuth tương tác và token cache bảo vệ bởi Windows.</span></div></div>
    {error && <div className="form-error">{error}</div>}
    <div className="modal-actions"><button type="button" className="button ghost" onClick={onClose}>Hủy</button><button className="button primary"><CalendarClock/>Lên lịch backup</button></div>
  </form></div>
}

function App() {
  const [data, setData] = useState({ jobs:[], events:[], summary:{total:0,active:0,complete:0,failed:0}, testMode:true })
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(false)
  const [query, setQuery] = useState('')
  const load = async () => { setLoading(true); try { setData(await (await fetch(`${API}/api/dashboard`)).json()) } finally { setLoading(false) } }
  useEffect(() => { load(); const timer=setInterval(load,5000); return()=>clearInterval(timer) }, [])
  const jobs = useMemo(() => data.jobs.filter(j => j.mailbox.includes(query.toLowerCase())), [data.jobs,query])
  const cards = [
    ['Tổng yêu cầu', data.summary.total, Database, 'neutral'], ['Đang xử lý', data.summary.active, Clock3, 'blue'],
    ['Hoàn tất', data.summary.complete, CheckCircle2, 'green'], ['Cần xử lý', data.summary.failed, CircleAlert, 'red']
  ]
  return <div className="app-shell">
    <aside><div className="brand"><div className="brand-mark"><Archive/></div><div><strong>InterLOG</strong><span>Mail Operations</span></div></div>
      <nav><span className="nav-label">VẬN HÀNH</span><a className="selected"><LayoutDashboard/>Dashboard</a><a><CalendarClock/>Lịch backup</a><a><HardDriveDownload/>PST Transfer</a><a><History/>Lịch sử</a><span className="nav-label">HỆ THỐNG</span><a><Server/>Worker VM</a><a><ShieldCheck/>Quyền & bảo mật</a></nav>
      <div className="worker-card"><div className="worker-top"><span className="live-dot"/><b>VM Worker</b><span>ONLINE</span></div><p>Test mode · Không truy cập mailbox thật</p><div className="worker-meta"><span>Queue</span><strong>{data.summary.active} jobs</strong></div></div>
    </aside>
    <main><header><div><span className="eyebrow">MAIL OPERATIONS CENTER</span><h1>Backup dashboard</h1><p>Lên lịch, theo dõi export PST và bàn giao về máy người dùng.</p></div><div className="header-actions"><button className="icon-btn" onClick={load}><RefreshCw className={loading?'spin':''}/></button><button className="button primary" onClick={()=>setModal(true)}><Plus/>Tạo yêu cầu</button></div></header>
      {data.testMode && <div className="test-banner"><ShieldCheck/><div><strong>TEST MODE đang bật</strong><span>Dashboard chỉ mô phỏng workflow, chưa gọi Purview, Outlook hoặc mailbox thật.</span></div></div>}
      <section className="stats">{cards.map(([label,value,Icon,tone])=><article className={`stat ${tone}`} key={label}><div><span>{label}</span><strong>{value}</strong><small>Toàn bộ lịch sử</small></div><div className="stat-icon"><Icon/></div></article>)}</section>
      <section className="content-grid"><div className="panel jobs-panel"><div className="panel-head"><div><h2>Yêu cầu gần đây</h2><p>Theo dõi toàn bộ vòng đời PST</p></div><div className="search"><Search/><input placeholder="Tìm theo email..." value={query} onChange={e=>setQuery(e.target.value)}/></div></div>
        <div className="table-wrap"><table><thead><tr><th>Mailbox / phạm vi</th><th>Lịch chạy</th><th>Trạng thái</th><th>Tiến độ</th><th>Engine</th><th/></tr></thead><tbody>{jobs.length===0?<tr><td colSpan="6" className="empty">Chưa có yêu cầu. Bấm “Tạo yêu cầu” để bắt đầu.</td></tr>:jobs.map(job=><tr key={job.id}><td><div className="mail-cell"><div className="mail-icon">{job.scope==='online_archive'?<Archive/>:<Inbox/>}</div><div><strong>{job.mailbox}</strong><span>{scopeNames[job.scope]}{job.folder_name?` · ${job.folder_name}`:''}</span></div></div></td><td><strong className="date">{formatDate(job.scheduled_at)}</strong><span className="sub">#{String(job.id).padStart(4,'0')}</span></td><td><Status value={job.status}/></td><td><div className="progress-row"><div className="progress"><i style={{width:`${job.progress}%`}}/></div><b>{job.progress}%</b></div></td><td><span className="engine">{job.export_engine==='purview'?'Purview':'Outlook'}</span></td><td><button className="row-action"><ChevronRight/></button></td></tr>)}</tbody></table></div>
      </div><div className="panel activity"><div className="panel-head"><div><h2>Hoạt động</h2><p>Log mới nhất từ SQLite</p></div></div><div className="timeline">{data.events.length===0?<div className="empty">Chưa có sự kiện.</div>:data.events.map(event=><div className="event" key={event.id}><i className={event.level.toLowerCase()}/><div><strong>{event.mailbox}</strong><p>{event.message}</p><span>{formatDate(event.created_at)}</span></div></div>)}</div></div></section>
    </main>{modal&&<NewJob onClose={()=>setModal(false)} onCreated={load}/>}</div>
}

createRoot(document.getElementById('root')).render(<App />)

