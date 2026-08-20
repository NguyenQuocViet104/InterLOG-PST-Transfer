import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Archive, CalendarClock, CheckCircle2, ChevronRight, CircleAlert, Clock3, Database, HardDriveDownload, History, Inbox, LayoutDashboard, Plus, RefreshCw, RotateCcw, Search, Server, ShieldCheck, X, XCircle } from 'lucide-react'
import './styles.css'

const API = import.meta.env.VITE_API_URL || ''
const scopes = { primary:'Mailbox chính', online_archive:'Online Archive', folder:'Thư mục cụ thể' }
const statusNames = { SCHEDULED:'Đã lên lịch', WAITING_OPERATOR:'Chờ IT export', EXPORTING:'Đang export', PST_READY:'PST sẵn sàng', WAITING_TRANSFER:'Chờ chuyển PST', TRANSFERRING:'Đang chuyển', VERIFYING:'Đang xác minh', COMPLETE:'Hoàn tất', FAILED:'Thất bại', CANCELLED:'Đã hủy' }
const filters = [['ALL','Tất cả'],['ACTIVE','Đang xử lý'],['WAITING_OPERATOR','Chờ IT'],['COMPLETE','Hoàn tất'],['FAILED','Lỗi']]
const fmtDate = v => v ? new Intl.DateTimeFormat('vi-VN',{dateStyle:'short',timeStyle:'short'}).format(new Date(v)) : '—'
const fmtBytes = n => !n ? '0 B' : `${(n/1024/1024/1024).toFixed(2)} GB`

function Status({value}) {
  const tone=value==='COMPLETE'?'success':value==='FAILED'?'danger':value==='CANCELLED'?'muted':'active'
  return <span className={`status ${tone}`}><i/>{statusNames[value]||value}</span>
}

function NewJob({onClose,onCreated,workers}) {
  const d=new Date(Date.now()+60000); d.setMinutes(d.getMinutes()-d.getTimezoneOffset())
  const [form,setForm]=useState({mailbox:'',scope:'online_archive',folder_name:'',export_engine:'outlook_manual',auth_mode:'interactive_oauth',scheduled_at:d.toISOString().slice(0,16),destination:'D:\\MAIL BACKUP',ticket:'',requested_by:'',assigned_worker:workers[0]?.id||'vm-worker-01',note:''})
  const [error,setError]=useState('')
  const submit=async e=>{e.preventDefault();setError('');const r=await fetch(`${API}/api/jobs`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...form,scheduled_at:new Date(form.scheduled_at).toISOString()})});if(!r.ok){const b=await r.json();setError(b.detail||'Không tạo được job');return}onCreated();onClose()}
  return <div className="modal-backdrop"><form className="modal" onSubmit={submit}>
    <div className="modal-head"><div><span className="eyebrow">YÊU CẦU MỚI</span><h2>Lên lịch backup mail</h2><p>IT chọn đúng mailbox, phạm vi và VM thực hiện.</p></div><button type="button" className="icon-btn" onClick={onClose}><X/></button></div>
    <div className="form-grid">
      <label className="wide">Email cần backup<input required type="email" placeholder="test-mailbox@company.com" value={form.mailbox} onChange={e=>setForm({...form,mailbox:e.target.value})}/></label>
      <label>Mã ticket<input placeholder="INC-000123" value={form.ticket} onChange={e=>setForm({...form,ticket:e.target.value})}/></label>
      <label>Người yêu cầu<input placeholder="Phòng IT / tên user" value={form.requested_by} onChange={e=>setForm({...form,requested_by:e.target.value})}/></label>
      <label>Phạm vi<select value={form.scope} onChange={e=>setForm({...form,scope:e.target.value})}><option value="online_archive">Online Archive</option><option value="primary">Mailbox chính</option><option value="folder">Thư mục cụ thể</option></select></label>
      <label>Tên thư mục<input disabled={form.scope!=='folder'} required={form.scope==='folder'} value={form.folder_name} onChange={e=>setForm({...form,folder_name:e.target.value})}/></label>
      <label>Quy trình<select value={form.export_engine} onChange={e=>setForm({...form,export_engine:e.target.value,auth_mode:e.target.value==='purview'?'app_only':'interactive_oauth'})}><option value="outlook_manual">Outlook Classic — IT export</option><option value="purview">Purview — tự động (chưa kích hoạt)</option></select></label>
      <label>Worker<select value={form.assigned_worker} onChange={e=>setForm({...form,assigned_worker:e.target.value})}>{workers.map(w=><option key={w.id} value={w.id}>{w.display_name}</option>)}</select></label>
      <label>Lịch chạy<input required type="datetime-local" value={form.scheduled_at} onChange={e=>setForm({...form,scheduled_at:e.target.value})}/></label>
      <label>Thư mục PST đích<input required value={form.destination} onChange={e=>setForm({...form,destination:e.target.value})}/></label>
      <label className="wide">Ghi chú<textarea rows="3" value={form.note} onChange={e=>setForm({...form,note:e.target.value})}/></label>
    </div>
    <div className="security-note"><ShieldCheck/><div><strong>Không lưu mật khẩu Microsoft 365</strong><span>Outlook fallback do IT thao tác; Purview production sẽ dùng certificate và RBAC.</span></div></div>
    {error&&<div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button ghost" onClick={onClose}>Hủy</button><button className="button primary"><CalendarClock/>Lên lịch</button></div>
  </form></div>
}

function Detail({id,onClose,onChanged}) {
  const [data,setData]=useState(null),[error,setError]=useState('')
  const load=async()=>setData(await (await fetch(`${API}/api/jobs/${id}`)).json())
  useEffect(()=>{load()},[id])
  const action=async(name,body)=>{setError('');const r=await fetch(`${API}/api/jobs/${id}/${name}`,{method:'POST',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});if(!r.ok){const b=await r.json();setError(b.detail||'Thao tác thất bại');return}await load();onChanged()}
  if(!data)return <div className="drawer-backdrop"><aside className="drawer">Đang tải...</aside></div>
  const j=data.job
  const ready=()=>{const path=prompt('Đường dẫn file PST đã export xong trên VM:',j.pst_path||'C:\\MailBackup\\user_archive.pst');if(path){const size=Number(prompt('Kích thước byte (có thể để 0):','0'))||0;action('operator-ready',{pst_path:path,size_bytes:size})}}
  return <div className="drawer-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><aside className="drawer">
    <div className="drawer-head"><div><span className="eyebrow">JOB #{String(j.id).padStart(4,'0')}</span><h2>{j.mailbox}</h2><Status value={j.status}/></div><button className="icon-btn" onClick={onClose}><X/></button></div>
    <div className="detail-progress"><div><strong>{j.progress}%</strong><span>{fmtBytes(j.bytes_done)} / {fmtBytes(j.bytes_total)}</span></div><div className="progress large"><i style={{width:`${j.progress}%`}}/></div></div>
    {j.error&&<div className="detail-error"><CircleAlert/><span>{j.error}</span></div>}
    <div className="detail-grid"><span>Phạm vi<b>{scopes[j.scope]}{j.folder_name?` · ${j.folder_name}`:''}</b></span><span>Lịch chạy<b>{fmtDate(j.scheduled_at)}</b></span><span>Ticket<b>{j.ticket||'—'}</b></span><span>Người yêu cầu<b>{j.requested_by||'—'}</b></span><span>Worker<b>{j.assigned_worker}</b></span><span>Engine<b>{j.export_engine==='purview'?'Purview':'Outlook Classic'}</b></span><span className="wide">PST / Đích<b>{j.pst_path||j.destination}</b></span></div>
    <div className="detail-actions">{j.status==='WAITING_OPERATOR'&&<button className="button primary" onClick={ready}><CheckCircle2/>PST đã export xong</button>}{!['COMPLETE','CANCELLED'].includes(j.status)&&<button className="button ghost" onClick={()=>action('retry')}><RotateCcw/>Thử lại / tiếp tục</button>}{!['COMPLETE','CANCELLED'].includes(j.status)&&<button className="button danger" onClick={()=>action('cancel')}><XCircle/>Hủy job</button>}</div>
    {error&&<div className="form-error">{error}</div>}
    <h3>Lịch sử xử lý</h3><div className="timeline detail-timeline">{data.events.map(e=><div className="event" key={e.id}><i className={e.level.toLowerCase()}/><div><p>{e.message}</p><span>{fmtDate(e.created_at)}</span></div></div>)}</div>
  </aside></div>
}

function App(){
  const [data,setData]=useState({jobs:[],events:[],workers:[],summary:{total:0,active:0,complete:0,failed:0},testMode:true}),[loading,setLoading]=useState(true),[modal,setModal]=useState(false),[selected,setSelected]=useState(null),[query,setQuery]=useState(''),[filter,setFilter]=useState('ALL')
  const load=async()=>{setLoading(true);try{setData(await(await fetch(`${API}/api/dashboard`)).json())}finally{setLoading(false)}}
  useEffect(()=>{load();const t=setInterval(load,5000);return()=>clearInterval(t)},[])
  const jobs=useMemo(() => {
    const needle=query.toLowerCase()
    return data.jobs.filter(j => {
      const matchesText=j.mailbox.includes(needle)||(j.ticket||'').toLowerCase().includes(needle)
      const matchesStatus=filter==='ALL'||(filter==='ACTIVE' ? !['COMPLETE','FAILED','CANCELLED'].includes(j.status) : j.status===filter)
      return matchesText&&matchesStatus
    })
  },[data.jobs,query,filter])
  const cards=[['Tổng yêu cầu',data.summary.total,Database,'neutral'],['Đang xử lý',data.summary.active,Clock3,'blue'],['Hoàn tất',data.summary.complete,CheckCircle2,'green'],['Cần xử lý',data.summary.failed,CircleAlert,'red']]
  const worker=data.workers[0]
  return <div className="app-shell"><aside><div className="brand"><div className="brand-mark"><Archive/></div><div><strong>InterLOG</strong><span>Mail Operations</span></div></div><nav><span className="nav-label">VẬN HÀNH</span><a className="selected"><LayoutDashboard/>Dashboard</a><a><CalendarClock/>Lịch backup</a><a><HardDriveDownload/>PST Transfer</a><a><History/>Lịch sử</a><span className="nav-label">HỆ THỐNG</span><a><Server/>Worker VM</a><a><ShieldCheck/>Quyền & bảo mật</a></nav><div className="worker-card"><div className="worker-top"><span className={`live-dot ${worker?.status!=='ONLINE'?'offline':''}`}/><b>{worker?.display_name||'VM Worker'}</b><span>{worker?.status||'OFFLINE'}</span></div><p>{worker?.machine_name||'Chưa kết nối'} · {worker?.detail||'Không có heartbeat'}</p><div className="worker-meta"><span>Queue</span><strong>{data.summary.active} jobs</strong></div></div></aside>
  <main><header><div><span className="eyebrow">MAIL OPERATIONS CENTER</span><h1>Backup dashboard</h1><p>IT lên lịch, theo dõi export PST và chuyển file về máy user.</p></div><div className="header-actions"><button className="icon-btn" onClick={load}><RefreshCw className={loading?'spin':''}/></button><button className="button primary" onClick={()=>setModal(true)}><Plus/>Tạo yêu cầu</button></div></header>
  {data.testMode&&<div className="test-banner"><ShieldCheck/><div><strong>TEST MODE đang bật</strong><span>Chỉ dùng mailbox giả/test; chưa gọi Purview, Outlook hay mailbox thật.</span></div></div>}
  <section className="stats">{cards.map(([l,v,I,t])=><article className={`stat ${t}`} key={l}><div><span>{l}</span><strong>{v}</strong><small>Toàn bộ lịch sử</small></div><div className="stat-icon"><I/></div></article>)}</section>
  <section className="content-grid"><div className="panel jobs-panel"><div className="panel-head expanded"><div><h2>Hàng đợi backup</h2><p>Nhấn vào một job để xem log và xử lý</p></div><div className="search"><Search/><input placeholder="Email hoặc ticket..." value={query} onChange={e=>setQuery(e.target.value)}/></div></div><div className="filter-bar">{filters.map(([v,l])=><button className={filter===v?'selected':''} onClick={()=>setFilter(v)} key={v}>{l}</button>)}</div><div className="table-wrap"><table><thead><tr><th>Mailbox / phạm vi</th><th>Lịch chạy</th><th>Trạng thái</th><th>Tiến độ</th><th>Worker</th><th/></tr></thead><tbody>{jobs.length===0?<tr><td colSpan="6" className="empty">Không có job phù hợp.</td></tr>:jobs.map(j=><tr key={j.id} className="clickable" onClick={()=>setSelected(j.id)}><td><div className="mail-cell"><div className="mail-icon">{j.scope==='online_archive'?<Archive/>:<Inbox/>}</div><div><strong>{j.mailbox}</strong><span>{scopes[j.scope]}{j.ticket?` · ${j.ticket}`:''}</span></div></div></td><td><strong className="date">{fmtDate(j.scheduled_at)}</strong><span className="sub">#{String(j.id).padStart(4,'0')}</span></td><td><Status value={j.status}/></td><td><div className="progress-row"><div className="progress"><i style={{width:`${j.progress}%`}}/></div><b>{j.progress}%</b></div></td><td><span className="engine">{j.assigned_worker}</span></td><td><button className="row-action"><ChevronRight/></button></td></tr>)}</tbody></table></div></div>
  <div className="panel activity"><div className="panel-head"><div><h2>Hoạt động</h2><p>Log mới nhất từ SQLite</p></div></div><div className="timeline">{data.events.length===0?<div className="empty">Chưa có sự kiện.</div>:data.events.map(e=><div className="event" key={e.id}><i className={e.level.toLowerCase()}/><div><strong>{e.mailbox}</strong><p>{e.message}</p><span>{fmtDate(e.created_at)}</span></div></div>)}</div></div></section></main>
  {modal&&<NewJob workers={data.workers} onClose={()=>setModal(false)} onCreated={load}/>} {selected&&<Detail id={selected} onClose={()=>setSelected(null)} onChanged={load}/>}</div>
}

createRoot(document.getElementById('root')).render(<App/>)
