import { useState, useEffect, createContext, useContext } from 'react'
import api from './api'

// ==================== КОНТЕКСТ АВТОРИЗАЦИИ ====================
const AuthContext = createContext(null)

function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (localStorage.getItem('token')) {
      api.get('/auth/me').then(r => setUser(r.data)).catch(() => localStorage.removeItem('token')).finally(() => setLoading(false))
    } else setLoading(false)
  }, [])

  const login = async (username, password) => {
    const r = await api.post('/auth/login', { username, password })
    localStorage.setItem('token', r.data.access_token)
    const me = await api.get('/auth/me')
    setUser(me.data)
  }

  const logout = () => { localStorage.removeItem('token'); setUser(null) }

  const isSueAdmin = user?.role_code === 'SUE_ADMIN'
  const isLabUser = user?.role_code === 'LAB_USER'
  const isEskAdmin = user?.role_code === 'ESK_ADMIN'
  const isResUser = user?.role_code === 'RES_USER'
  const isEskUser = user?.role_code === 'ESK_USER'
  
  const canUpload = isLabUser
  const canMove = isSueAdmin || isEskAdmin
  const canDelete = isSueAdmin
  const canManageUsers = isSueAdmin
  const canApprove = isResUser || isSueAdmin

  return <AuthContext.Provider value={{ 
    user, loading, login, logout, 
    isSueAdmin, isLabUser, isEskAdmin, isResUser, isEskUser,
    canUpload, canMove, canDelete, canManageUsers, canApprove 
  }}>{children}</AuthContext.Provider>
}

const useAuth = () => useContext(AuthContext)

// ==================== ГЛАВНЫЙ КОМПОНЕНТ ====================
export default function App() {
  return <AuthProvider><Main /></AuthProvider>
}

function Main() {
  const { user, loading } = useAuth()
  const [page, setPage] = useState('home')

  if (loading) return <div className="min-h-screen flex items-center justify-center"><div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" /></div>
  if (!user) return <LoginPage />

  return (
    <div className="min-h-screen flex bg-gray-100">
      <Sidebar page={page} setPage={setPage} />
      <div className="flex-1 ml-56">
        <Header />
        <div className="p-6">
          {page === 'home' && <HomePage setPage={setPage} />}
          {page === 'pu' && <PUListPage />}
          {page === 'upload' && <UploadPage />}
          {page === 'approval' && <ApprovalPage />}
          {page === 'settings' && <SettingsPage />}
        </div>
      </div>
    </div>
  )
}

// ==================== САЙДБАР ====================
function Sidebar({ page, setPage }) {
  const { user, logout, canUpload, canManageUsers, canApprove, isEskUser, isEskAdmin } = useAuth()
  const [pendingCount, setPendingCount] = useState(0)

  useEffect(() => {
    if (canApprove) {
      api.get('/pu/pending-approval').then(r => setPendingCount(r.data.length)).catch(() => {})
    }
  }, [canApprove, page])

  const items = [
    { id: 'home', label: '🏠 Главная', show: true },
    { id: 'pu', label: '📦 Приборы учета', show: true },
    { id: 'upload', label: '📤 Загрузка', show: canUpload },
    { id: 'approval', label: '✅ Согласование', show: canApprove, badge: pendingCount },
    { id: 'settings', label: '⚙️ Настройки', show: canManageUsers },
  ].filter(i => i.show)

  return (
    <aside className="fixed left-0 top-0 h-full w-56 bg-slate-800 text-white flex flex-col">
      <div className="p-4 border-b border-slate-700">
        <div className="font-bold text-lg">ПУ Система</div>
        <div className="text-xs text-slate-400">v2.0</div>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {items.map(i => (
          <button key={i.id} onClick={() => setPage(i.id)} className={`w-full text-left px-3 py-2 rounded-lg flex items-center justify-between ${page === i.id ? 'bg-blue-600' : 'hover:bg-slate-700'}`}>
            <span>{i.label}</span>
            {i.badge > 0 && <span className="bg-red-500 text-white text-xs px-2 py-0.5 rounded-full">{i.badge}</span>}
          </button>
        ))}
      </nav>
      <div className="p-3 border-t border-slate-700">
        <div className="bg-slate-700/50 rounded-lg p-2 mb-2">
          <div className="font-medium truncate">{user?.full_name}</div>
          <div className="text-xs text-slate-400">{user?.unit_name}</div>
          <div className="text-xs text-slate-500">{user?.role_name}</div>
        </div>
        <button onClick={logout} className="w-full px-3 py-2 text-left hover:bg-slate-700 rounded-lg">🚪 Выйти</button>
      </div>
    </aside>
  )
}

function Header() {
  const { user } = useAuth()
  return <header className="h-16 bg-white border-b px-6 flex items-center justify-between sticky top-0 z-10">
    <h1 className="font-semibold">{user?.unit_name || 'Система учета ПУ'}</h1>
    <span className="text-sm text-gray-500">{user?.role_name}</span>
  </header>
}

// ==================== СТРАНИЦА ЛОГИНА ====================
function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try { await login(username, password) } 
    catch (err) { setError(err.response?.data?.detail || 'Ошибка входа') }
    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-800 to-slate-900 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl p-8 w-full max-w-md">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">⚡</div>
          <h1 className="text-2xl font-bold">Система учета ПУ</h1>
          <p className="text-gray-500 text-sm">Версия 2.0</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input type="text" placeholder="Логин" value={username} onChange={e => setUsername(e.target.value)} className="w-full px-4 py-3 border rounded-lg" />
          <input type="password" placeholder="Пароль" value={password} onChange={e => setPassword(e.target.value)} className="w-full px-4 py-3 border rounded-lg" />
          {error && <div className="text-red-500 text-sm">{error}</div>}
          <button type="submit" disabled={loading} className="w-full py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {loading ? 'Вход...' : 'Войти'}
          </button>
        </form>
        <div className="mt-4 p-3 bg-gray-50 rounded-lg text-sm text-gray-500">
          <b>Тестовые:</b><br/>
          admin/admin123 — СУЭ<br/>
          lab/lab123 — Лаборатория<br/>
          esk/esk123 — ЭСК Админ
        </div>
      </div>
    </div>
  )
}

// ==================== ГЛАВНАЯ СТРАНИЦА ====================
function HomePage({ setPage }) {
  const { user, canUpload, canManageUsers, canApprove } = useAuth()
  const [stats, setStats] = useState(null)

  useEffect(() => { api.get('/pu/dashboard').then(r => setStats(r.data)) }, [])

  const shortcuts = [
    { id: 'pu', icon: '📦', label: 'Приборы учета', desc: 'Просмотр и управление', show: true },
    { id: 'upload', icon: '📤', label: 'Загрузить реестр', desc: 'Импорт из Excel', show: canUpload },
    { id: 'approval', icon: '✅', label: 'Согласование', desc: 'СМР от ЭСК', show: canApprove },
    { id: 'settings', icon: '⚙️', label: 'Настройки', desc: 'Пользователи', show: canManageUsers },
  ].filter(s => s.show)

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-2xl p-6 text-white">
        <h1 className="text-2xl font-bold">Добро пожаловать, {user?.full_name}!</h1>
        <p className="text-blue-100">{user?.unit_name} • {user?.role_name}</p>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard label="Всего ПУ" value={stats.total_pu} color="blue" />
          <StatCard label="На складе" value={stats.sklad} color="gray" />
          <StatCard label="Техприс" value={stats.techpris} color="green" />
          <StatCard label="Замена" value={stats.zamena} color="yellow" />
          <StatCard label="ИЖЦ" value={stats.izhc} color="purple" />
          <StatCard label="Установлено" value={stats.installed} color="emerald" />
        </div>
      )}

      {stats?.pending_approval > 0 && (
        <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 flex items-center justify-between">
          <div>
            <span className="text-orange-700 font-medium">🔔 На согласовании: {stats.pending_approval}</span>
            <p className="text-orange-600 text-sm">Требуется проверка СМР от ЭСК</p>
          </div>
          <button onClick={() => setPage('approval')} className="px-4 py-2 bg-orange-500 text-white rounded-lg">Перейти</button>
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold mb-4">Быстрый доступ</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {shortcuts.map(s => (
            <button key={s.id} onClick={() => setPage(s.id)} className="bg-white p-6 rounded-xl border hover:shadow-md text-left">
              <div className="text-3xl mb-3">{s.icon}</div>
              <div className="font-semibold">{s.label}</div>
              <div className="text-sm text-gray-500">{s.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {stats?.recent_registers?.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">Последние загрузки</h2>
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50"><tr><th className="px-4 py-3 text-left">Файл</th><th className="px-4 py-3 text-left">Кол-во</th><th className="px-4 py-3 text-left">Дата</th></tr></thead>
              <tbody>
                {stats.recent_registers.map(r => (
                  <tr key={r.id} className="border-t"><td className="px-4 py-3">{r.filename}</td><td className="px-4 py-3">{r.items_count}</td><td className="px-4 py-3 text-gray-500">{new Date(r.uploaded_at).toLocaleDateString('ru')}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, color = 'blue' }) {
  const colors = {
    blue: 'bg-blue-50 text-blue-700',
    gray: 'bg-gray-50 text-gray-700',
    green: 'bg-green-50 text-green-700',
    yellow: 'bg-yellow-50 text-yellow-700',
    purple: 'bg-purple-50 text-purple-700',
    emerald: 'bg-emerald-50 text-emerald-700',
  }
  return <div className={`rounded-xl p-5 ${colors[color]}`}><div className="text-2xl font-bold">{value}</div><div className="text-sm opacity-80">{label}</div></div>
}

// ==================== СПИСОК ПУ ====================
function PUListPage() {
  const { canMove, canDelete, isSueAdmin, isEskAdmin } = useAuth()
  const [items, setItems] = useState([])
  const [units, setUnits] = useState([])
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [unitFilter, setUnitFilter] = useState('')
  const [excludeEsk, setExcludeEsk] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [selected, setSelected] = useState([])
  const [moveModal, setMoveModal] = useState(false)
  const [deleteModal, setDeleteModal] = useState(false)
  const [cardModal, setCardModal] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => { api.get('/units').then(r => setUnits(r.data)) }, [])
  useEffect(() => { load() }, [page, status, unitFilter, excludeEsk])

  const load = async () => {
    setLoading(true)
    const params = { page, size: 50 }
    if (search) params.search = search
    if (status) params.status = status
    if (unitFilter) params.unit_id = unitFilter
    if (excludeEsk) params.exclude_esk = true
    const r = await api.get('/pu/items', { params })
    setItems(r.data.items)
    setTotal(r.data.total)
    setPages(r.data.pages)
    setLoading(false)
  }

  const handleMove = async (toUnitId, comment) => {
    await api.post('/pu/move', { pu_item_ids: selected, to_unit_id: toUnitId, comment })
    setSelected([])
    setMoveModal(false)
    load()
  }

  const handleDelete = async (adminCode) => {
    try {
      await api.post('/pu/delete', { pu_item_ids: selected, admin_code: adminCode })
      setSelected([])
      setDeleteModal(false)
      load()
    } catch (err) {
      alert(err.response?.data?.detail || 'Ошибка удаления')
    }
  }

  const statusLabels = { SKLAD: 'Склад', TECHPRIS: 'Техприс', ZAMENA: 'Замена', IZHC: 'ИЖЦ', INSTALLED: 'Установлен' }
  const statusColors = { SKLAD: 'bg-gray-100', TECHPRIS: 'bg-green-100 text-green-800', ZAMENA: 'bg-yellow-100 text-yellow-800', IZHC: 'bg-purple-100 text-purple-800', INSTALLED: 'bg-emerald-100 text-emerald-800' }

  // Фильтруем подразделения для перемещения по роли
  const moveUnits = units.filter(u => {
    if (isSueAdmin) return u.unit_type === 'RES'
    if (isEskAdmin) return u.unit_type === 'ESK' || u.unit_type === 'ESK_UNIT'
    return false
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div><h1 className="text-2xl font-bold">Приборы учета</h1><p className="text-gray-500">Всего: {total}</p></div>
        <button onClick={load} className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200">🔄 Обновить</button>
      </div>

      <div className="bg-white rounded-xl border p-4 flex flex-wrap gap-3">
        <input type="text" placeholder="Поиск по номеру ПУ..." value={search} onChange={e => setSearch(e.target.value)} className="flex-1 min-w-48 px-3 py-2 border rounded-lg" />
        <button onClick={() => { setPage(1); load() }} className="px-4 py-2 bg-blue-600 text-white rounded-lg">Найти</button>
        <select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }} className="px-3 py-2 border rounded-lg">
          <option value="">Все статусы</option>
          {Object.entries(statusLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        {(isSueAdmin || isEskAdmin) && (
          <select value={unitFilter} onChange={e => { setUnitFilter(e.target.value); setPage(1) }} className="px-3 py-2 border rounded-lg">
            <option value="">Все подразделения</option>
            {units.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        )}
        {isSueAdmin && (
          <label className="flex items-center gap-2 px-3 py-2 border rounded-lg cursor-pointer">
            <input type="checkbox" checked={excludeEsk} onChange={e => { setExcludeEsk(e.target.checked); setPage(1) }} />
            <span>Без ЭСК</span>
          </label>
        )}
      </div>

      {selected.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-center justify-between">
          <span className="text-blue-700 font-medium">Выбрано: {selected.length}</span>
          <div className="flex gap-2">
            {canMove && <button onClick={() => setMoveModal(true)} className="px-4 py-2 bg-blue-600 text-white rounded-lg">➡️ Переместить</button>}
            {canDelete && <button onClick={() => setDeleteModal(true)} className="px-4 py-2 bg-red-600 text-white rounded-lg">🗑️ Удалить</button>}
            <button onClick={() => setSelected([])} className="px-4 py-2 bg-gray-100 rounded-lg">Отменить</button>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border overflow-hidden">
        {loading ? <div className="p-8 text-center">Загрузка...</div> : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                {canMove && <th className="w-10 px-4 py-3"><input type="checkbox" onChange={e => setSelected(e.target.checked ? items.map(i => i.id) : [])} checked={selected.length === items.length && items.length > 0} /></th>}
                <th className="px-4 py-3 text-left">Серийный номер</th>
                <th className="px-4 py-3 text-left">Тип</th>
                <th className="px-4 py-3 text-left">Подразделение</th>
                <th className="px-4 py-3 text-left">Статус</th>
                <th className="px-4 py-3 text-left">№ ТЗ</th>
                <th className="px-4 py-3 text-left">Дата</th>
                <th className="w-16"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(i => (
                <tr key={i.id} className="border-t hover:bg-gray-50">
                  {canMove && <td className="px-4 py-3"><input type="checkbox" checked={selected.includes(i.id)} onChange={() => setSelected(s => s.includes(i.id) ? s.filter(x => x !== i.id) : [...s, i.id])} /></td>}
                  <td className="px-4 py-3 font-mono">{i.serial_number}</td>
                  <td className="px-4 py-3 text-gray-600 max-w-xs truncate" title={i.pu_type}>{i.pu_type || '—'}</td>
                  <td className="px-4 py-3">{i.current_unit_name || '—'}</td>
                  <td className="px-4 py-3"><span className={`px-2 py-1 rounded-full text-xs ${statusColors[i.status] || 'bg-gray-100'}`}>{statusLabels[i.status] || i.status}</span></td>
                  <td className="px-4 py-3">{i.tz_number || '—'}</td>
                  <td className="px-4 py-3 text-gray-500">{i.uploaded_at ? new Date(i.uploaded_at).toLocaleDateString('ru') : '—'}</td>
                  <td className="px-4 py-3"><button onClick={() => setCardModal(i.id)} className="text-blue-600 hover:underline">📋</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {pages > 1 && (
          <div className="px-4 py-3 border-t flex justify-between items-center">
            <span className="text-sm text-gray-500">Страница {page} из {pages}</span>
            <div className="flex gap-2">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 border rounded disabled:opacity-50">←</button>
              <button onClick={() => setPage(p => Math.min(pages, p + 1))} disabled={page === pages} className="px-3 py-1 border rounded disabled:opacity-50">→</button>
            </div>
          </div>
        )}
      </div>

      {moveModal && <MoveModal units={moveUnits} onClose={() => setMoveModal(false)} onMove={handleMove} count={selected.length} />}
      {deleteModal && <DeleteModal onClose={() => setDeleteModal(false)} onDelete={handleDelete} count={selected.length} />}
      {cardModal && <PUCardModal itemId={cardModal} onClose={() => { setCardModal(null); load() }} />}
    </div>
  )
}

function MoveModal({ units, onClose, onMove, count }) {
  const [unitId, setUnitId] = useState('')
  const [comment, setComment] = useState('')
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold mb-4">Переместить {count} ПУ</h2>
        <select value={unitId} onChange={e => setUnitId(e.target.value)} className="w-full px-3 py-2 border rounded-lg mb-4">
          <option value="">Выберите подразделение...</option>
          {units.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
        <textarea value={comment} onChange={e => setComment(e.target.value)} placeholder="Комментарий" className="w-full px-3 py-2 border rounded-lg mb-4" rows={3} />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 bg-gray-100 rounded-lg">Отмена</button>
          <button onClick={() => unitId && onMove(parseInt(unitId), comment)} className="px-4 py-2 bg-blue-600 text-white rounded-lg">Переместить</button>
        </div>
      </div>
    </div>
  )
}

function DeleteModal({ onClose, onDelete, count }) {
  const [code, setCode] = useState('')
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold mb-4 text-red-600">🗑️ Удалить {count} ПУ?</h2>
        <p className="text-gray-600 mb-4">Это действие нельзя отменить. Введите код администратора:</p>
        <input type="password" placeholder="Код админа" value={code} onChange={e => setCode(e.target.value)} className="w-full px-3 py-2 border rounded-lg mb-4" />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 bg-gray-100 rounded-lg">Отмена</button>
          <button onClick={() => code && onDelete(code)} className="px-4 py-2 bg-red-600 text-white rounded-lg">Удалить</button>
        </div>
      </div>
    </div>
  )
}

// ==================== КАРТОЧКА ПУ ====================
function PUCardModal({ itemId, onClose }) {
  const { isSueAdmin, isResUser, isEskUser, isEskAdmin } = useAuth()
  const [item, setItem] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [ttrRes, setTtrRes] = useState([])
  const [ttrEsk, setTtrEsk] = useState([])

  useEffect(() => {
    api.get(`/pu/items/${itemId}`).then(r => { setItem(r.data); setLoading(false) })
    api.get('/ttr/res').then(r => setTtrRes(r.data))
    api.get('/ttr/esk').then(r => setTtrEsk(r.data))
  }, [itemId])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.put(`/pu/items/${itemId}`, item)
      onClose()
    } catch (err) {
      alert(err.response?.data?.detail || 'Ошибка сохранения')
    }
    setSaving(false)
  }

  const update = (field, value) => setItem({ ...item, [field]: value })

  if (loading) return <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"><div className="bg-white rounded-xl p-8">Загрузка...</div></div>

  const isEsk = item?.current_unit_type === 'ESK_UNIT' || item?.current_unit_type === 'ESK'
  const isRes = item?.current_unit_type === 'RES'
  const canEdit = isSueAdmin || (isResUser && isRes) || ((isEskUser || isEskAdmin) && isEsk)

  const statusOptions = [
    { value: 'SKLAD', label: 'На складе' },
    { value: 'TECHPRIS', label: 'Техприс' },
    { value: 'ZAMENA', label: 'Замена' },
    { value: 'IZHC', label: 'ИЖЦ' },
    { value: 'INSTALLED', label: 'Установлен' },
  ]

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
          <h2 className="text-lg font-semibold">Карточка ПУ</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
        </div>
        
        <div className="p-6 space-y-4">
          {/* Основное */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">Серийный номер</label>
              <input type="text" value={item.serial_number || ''} disabled className="w-full px-3 py-2 border rounded-lg bg-gray-50" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">Подразделение</label>
              <input type="text" value={item.current_unit_name || ''} disabled className="w-full px-3 py-2 border rounded-lg bg-gray-50" />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">Тип ПУ</label>
            <input type="text" value={item.pu_type || ''} disabled className="w-full px-3 py-2 border rounded-lg bg-gray-50" />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">Статус *</label>
              <select value={item.status || ''} onChange={e => update('status', e.target.value)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg">
                {statusOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">Фазность</label>
              <select value={item.faza || ''} onChange={e => update('faza', e.target.value)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg">
                <option value="">—</option>
                <option value="1ф">1 фаза</option>
                <option value="3ф">3 фазы</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">Напряжение</label>
              <select value={item.voltage || ''} onChange={e => update('voltage', e.target.value)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg">
                <option value="">—</option>
                <option value="0.23">0,23 кВ</option>
                <option value="0.4">0,4 кВ</option>
                <option value="6">6 кВ</option>
                <option value="10">10 кВ</option>
              </select>
            </div>
          </div>

          {/* Для Техприс */}
          {(item.status === 'TECHPRIS' || isEsk) && (
            <>
              <hr />
              <h3 className="font-medium">Данные техприсоединения</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">Номер договора</label>
                  <input type="text" value={item.contract_number || ''} onChange={e => update('contract_number', e.target.value)} disabled={!canEdit} placeholder="ххххх-хх-хххххххх-х" className="w-full px-3 py-2 border rounded-lg" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">Мощность, кВт</label>
                  <input type="number" value={item.power || ''} onChange={e => update('power', parseFloat(e.target.value) || null)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">Дата заключения</label>
                  <input type="date" value={item.contract_date || ''} onChange={e => update('contract_date', e.target.value)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">Планируемая дата</label>
                  <input type="date" value={item.plan_date || ''} onChange={e => update('plan_date', e.target.value)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Потребитель</label>
                <input type="text" value={item.consumer || ''} onChange={e => update('consumer', e.target.value)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Адрес</label>
                <textarea value={item.address || ''} onChange={e => update('address', e.target.value)} disabled={!canEdit} rows={2} className="w-full px-3 py-2 border rounded-lg" />
              </div>
            </>
          )}

          {/* Для Замена и ИЖЦ */}
          {(item.status === 'ZAMENA' || item.status === 'IZHC') && (
            <>
              <hr />
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Лицевой счет (ЛС)</label>
                <input type="text" value={item.ls_number || ''} onChange={e => update('ls_number', e.target.value)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg" />
              </div>
            </>
          )}

          {/* ТТР для РЭС */}
          {isRes && item.status !== 'SKLAD' && (
            <>
              <hr />
              <h3 className="font-medium">ТТР (для РЭС)</h3>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">ТТР орг. учета</label>
                  <select value={item.ttr_ou_id || ''} onChange={e => update('ttr_ou_id', parseInt(e.target.value) || null)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg">
                    <option value="">—</option>
                    {ttrRes.filter(t => t.ttr_type === 'OU').map(t => <option key={t.id} value={t.id}>{t.code}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">ТТР обуст. линии</label>
                  <select value={item.ttr_ol_id || ''} onChange={e => update('ttr_ol_id', parseInt(e.target.value) || null)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg">
                    <option value="">—</option>
                    {ttrRes.filter(t => t.ttr_type === 'OL').map(t => <option key={t.id} value={t.id}>{t.code}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">ТТР распред. щита</label>
                  <select value={item.ttr_or_id || ''} onChange={e => update('ttr_or_id', parseInt(e.target.value) || null)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg">
                    <option value="">—</option>
                    {ttrRes.filter(t => t.ttr_type === 'OR').map(t => <option key={t.id} value={t.id}>{t.code}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">СМР выполнил</label>
                  <select value={item.smr_executor || ''} onChange={e => update('smr_executor', e.target.value)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg">
                    <option value="">—</option>
                    <option value="РСК">РСК</option>
                    <option value="ЭСК">ЭСК</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">Дата СМР</label>
                  <input type="date" value={item.smr_date || ''} onChange={e => update('smr_date', e.target.value)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg" />
                </div>
              </div>
            </>
          )}

          {/* ТТР для ЭСК */}
          {isEsk && (
            <>
              <hr />
              <h3 className="font-medium">ТТР (для ЭСК)</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">ТТР орг. учета (ЭСК)</label>
                  <select value={item.ttr_esk_id || ''} onChange={e => update('ttr_esk_id', parseInt(e.target.value) || null)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg">
                    <option value="">—</option>
                    {ttrEsk.map(t => <option key={t.id} value={t.id}>{t.code} — {t.price} ₽</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">Трубостойка</label>
                  <select value={item.trubostoyka ? 'true' : 'false'} onChange={e => update('trubostoyka', e.target.value === 'true')} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg">
                    <option value="false">Нет</option>
                    <option value="true">Да</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Дата СМР</label>
                <input type="date" value={item.smr_date || ''} onChange={e => update('smr_date', e.target.value)} disabled={!canEdit} className="w-full px-3 py-2 border rounded-lg" />
              </div>
            </>
          )}

          {/* Номер ТЗ */}
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">Номер ТЗ / Заявки</label>
            <input type="text" value={item.tz_number || item.request_number || ''} disabled className="w-full px-3 py-2 border rounded-lg bg-gray-50" />
          </div>

          {/* Согласование */}
          {item.approval_status && (
            <div className={`p-3 rounded-lg ${item.approval_status === 'APPROVED' ? 'bg-green-50 text-green-700' : item.approval_status === 'PENDING' ? 'bg-yellow-50 text-yellow-700' : 'bg-gray-50'}`}>
              Статус согласования: {item.approval_status === 'APPROVED' ? '✅ Согласовано' : item.approval_status === 'PENDING' ? '⏳ На согласовании' : '—'}
            </div>
          )}
        </div>

        {canEdit && (
          <div className="sticky bottom-0 bg-gray-50 border-t px-6 py-4 flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 bg-gray-200 rounded-lg">Отмена</button>
            <button onClick={handleSave} disabled={saving} className="px-4 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">{saving ? 'Сохранение...' : 'Сохранить'}</button>
          </div>
        )}
      </div>
    </div>
  )
}

// ==================== ЗАГРУЗКА РЕЕСТРА ====================
function UploadPage() {
  const { canUpload } = useAuth()
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [registers, setRegisters] = useState([])

  useEffect(() => { api.get('/pu/registers').then(r => setRegisters(r.data)) }, [])

  const handleUpload = async () => {
    if (!file) return
    setLoading(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const r = await api.post('/pu/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      setResult(r.data)
      setFile(null)
      api.get('/pu/registers').then(r => setRegisters(r.data))
    } catch (err) {
      alert(err.response?.data?.detail || 'Ошибка')
    }
    setLoading(false)
  }

  if (!canUpload) return <div className="text-center py-12 text-gray-500">Нет доступа</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Загрузка реестра ПУ</h1>

      <div className="bg-white rounded-xl border p-8">
        {result ? (
          <div className="text-center">
            <div className="text-4xl mb-4">✅</div>
            <h3 className="text-xl font-semibold">Загружено {result.items_count} ПУ</h3>
            <p className="text-gray-500">Файл: {result.filename}</p>
            <button onClick={() => setResult(null)} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg">Загрузить ещё</button>
          </div>
        ) : (
          <div className="text-center">
            <div className="text-4xl mb-4">📊</div>
            {file ? <p className="mb-4 font-medium">{file.name}</p> : <p className="mb-4 text-gray-500">Выберите Excel файл (.xlsx, .xls)</p>}
            <div className="flex justify-center gap-3">
              <label className="px-4 py-2 bg-gray-100 rounded-lg cursor-pointer hover:bg-gray-200">
                {file ? 'Выбрать другой' : 'Выбрать файл'}
                <input type="file" accept=".xlsx,.xls" onChange={e => setFile(e.target.files[0])} className="hidden" />
              </label>
              {file && <button onClick={handleUpload} disabled={loading} className="px-4 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">{loading ? 'Загрузка...' : 'Загрузить'}</button>}
            </div>
            <p className="mt-4 text-sm text-gray-400">Ожидаемые колонки: Заводской номер ПУ, Тип прибора учета, Подразделение</p>
          </div>
        )}
      </div>

      {registers.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">История загрузок</h2>
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50"><tr><th className="px-4 py-3 text-left">Файл</th><th className="px-4 py-3 text-left">Кол-во</th><th className="px-4 py-3 text-left">Дата</th></tr></thead>
              <tbody>
                {registers.map(r => <tr key={r.id} className="border-t"><td className="px-4 py-3">{r.filename}</td><td className="px-4 py-3">{r.items_count}</td><td className="px-4 py-3 text-gray-500">{new Date(r.uploaded_at).toLocaleString('ru')}</td></tr>)}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// ==================== СОГЛАСОВАНИЕ ====================
function ApprovalPage() {
  const { canApprove } = useAuth()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { load() }, [])

  const load = () => {
    setLoading(true)
    api.get('/pu/pending-approval').then(r => { setItems(r.data); setLoading(false) })
  }

  const handleApprove = async (id) => {
    try {
      await api.post(`/pu/items/${id}/approve`)
      load()
    } catch (err) {
      alert(err.response?.data?.detail || 'Ошибка')
    }
  }

  if (!canApprove) return <div className="text-center py-12 text-gray-500">Нет доступа</div>

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">Согласование СМР</h1>
          <p className="text-gray-500">ПУ от ЭСК на проверку</p>
        </div>
        <button onClick={load} className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200">🔄 Обновить</button>
      </div>

      <div className="bg-white rounded-xl border overflow-hidden">
        {loading ? <div className="p-8 text-center">Загрузка...</div> : items.length === 0 ? (
          <div className="p-8 text-center text-gray-500">Нет ПУ на согласовании</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left">Серийный номер</th>
                <th className="px-4 py-3 text-left">Тип</th>
                <th className="px-4 py-3 text-left">Подразделение</th>
                <th className="px-4 py-3 text-left">Договор</th>
                <th className="px-4 py-3 text-left">Потребитель</th>
                <th className="w-32"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(i => (
                <tr key={i.id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono">{i.serial_number}</td>
                  <td className="px-4 py-3 text-gray-600 max-w-xs truncate">{i.pu_type || '—'}</td>
                  <td className="px-4 py-3">{i.current_unit_name || '—'}</td>
                  <td className="px-4 py-3">{i.contract_number || '—'}</td>
                  <td className="px-4 py-3">{i.consumer || '—'}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => handleApprove(i.id)} className="px-3 py-1 bg-green-600 text-white rounded-lg text-sm">✓ Согласовать</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ==================== НАСТРОЙКИ ====================
function SettingsPage() {
  const { canManageUsers, isSueAdmin } = useAuth()
  const [tab, setTab] = useState('users')
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState([])
  const [units, setUnits] = useState([])
  const [modal, setModal] = useState(null)
  const [clearModal, setClearModal] = useState(false)

  useEffect(() => {
    if (canManageUsers) {
      api.get('/users').then(r => setUsers(r.data))
      api.get('/roles').then(r => setRoles(r.data))
      api.get('/units').then(r => setUnits(r.data))
    }
  }, [canManageUsers])

  const toggleActive = async (u) => {
    await api.put(`/users/${u.id}`, { is_active: !u.is_active })
    api.get('/users').then(r => setUsers(r.data))
  }

  const handleSave = async (data) => {
    if (modal.user) {
      await api.put(`/users/${modal.user.id}`, data)
    } else {
      await api.post('/users', data)
    }
    api.get('/users').then(r => setUsers(r.data))
    setModal(null)
  }

  const handleClearDB = async (code) => {
    try {
      await api.post('/pu/clear-database', { admin_code: code })
      alert('База очищена')
      setClearModal(false)
    } catch (err) {
      alert(err.response?.data?.detail || 'Ошибка')
    }
  }

  if (!canManageUsers) return <div className="text-center py-12 text-gray-500">Нет доступа</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Настройки</h1>

      <div className="flex gap-2 border-b">
        <button onClick={() => setTab('users')} className={`px-4 py-2 border-b-2 ${tab === 'users' ? 'border-blue-600 text-blue-600' : 'border-transparent'}`}>Пользователи</button>
        {isSueAdmin && <button onClick={() => setTab('system')} className={`px-4 py-2 border-b-2 ${tab === 'system' ? 'border-blue-600 text-blue-600' : 'border-transparent'}`}>Система</button>}
      </div>

      {tab === 'users' && (
        <>
          <div className="flex justify-end">
            <button onClick={() => setModal({ user: null })} className="px-4 py-2 bg-blue-600 text-white rounded-lg">➕ Добавить</button>
          </div>

          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50"><tr><th className="px-4 py-3 text-left">Логин</th><th className="px-4 py-3 text-left">ФИО</th><th className="px-4 py-3 text-left">Роль</th><th className="px-4 py-3 text-left">Подразделение</th><th className="px-4 py-3 text-left">Статус</th><th className="w-24"></th></tr></thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} className={`border-t ${!u.is_active ? 'opacity-50' : ''}`}>
                    <td className="px-4 py-3 font-medium">{u.username}</td>
                    <td className="px-4 py-3">{u.full_name}</td>
                    <td className="px-4 py-3">{u.role?.name}</td>
                    <td className="px-4 py-3">{u.unit?.name || '—'}</td>
                    <td className="px-4 py-3"><span className={`px-2 py-1 rounded-full text-xs ${u.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100'}`}>{u.is_active ? 'Активен' : 'Неактивен'}</span></td>
                    <td className="px-4 py-3">
                      <button onClick={() => setModal({ user: u })} className="mr-2">✏️</button>
                      <button onClick={() => toggleActive(u)}>{u.is_active ? '🚫' : '✅'}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'system' && (
        <div className="bg-white rounded-xl border p-6 space-y-4">
          <h2 className="font-semibold text-red-600">⚠️ Опасная зона</h2>
          <div className="flex items-center justify-between p-4 bg-red-50 rounded-lg">
            <div>
              <div className="font-medium">Очистить базу данных</div>
              <div className="text-sm text-gray-500">Удалить все ПУ и загрузки</div>
            </div>
            <button onClick={() => setClearModal(true)} className="px-4 py-2 bg-red-600 text-white rounded-lg">Очистить</button>
          </div>
        </div>
      )}

      {modal && <UserModal user={modal.user} roles={roles} units={units} onClose={() => setModal(null)} onSave={handleSave} />}
      {clearModal && <ClearDBModal onClose={() => setClearModal(false)} onClear={handleClearDB} />}
    </div>
  )
}

function UserModal({ user, roles, units, onClose, onSave }) {
  const [form, setForm] = useState({ username: user?.username || '', password: '', full_name: user?.full_name || '', role_id: user?.role?.id || '', unit_id: user?.unit?.id || '' })
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold mb-4">{user ? 'Редактировать' : 'Новый пользователь'}</h2>
        <div className="space-y-3">
          <input type="text" placeholder="Логин" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} disabled={!!user} className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-100" />
          {!user && <input type="password" placeholder="Пароль" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} className="w-full px-3 py-2 border rounded-lg" />}
          <input type="text" placeholder="ФИО" value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} className="w-full px-3 py-2 border rounded-lg" />
          <select value={form.role_id} onChange={e => setForm({ ...form, role_id: e.target.value })} className="w-full px-3 py-2 border rounded-lg">
            <option value="">Выберите роль...</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          <select value={form.unit_id} onChange={e => setForm({ ...form, unit_id: e.target.value })} className="w-full px-3 py-2 border rounded-lg">
            <option value="">Без подразделения</option>
            {units.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-4 py-2 bg-gray-100 rounded-lg">Отмена</button>
          <button onClick={() => onSave({ ...form, role_id: parseInt(form.role_id), unit_id: form.unit_id ? parseInt(form.unit_id) : null })} className="px-4 py-2 bg-blue-600 text-white rounded-lg">Сохранить</button>
        </div>
      </div>
    </div>
  )
}

function ClearDBModal({ onClose, onClear }) {
  const [code, setCode] = useState('')
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold mb-4 text-red-600">⚠️ Очистка базы данных</h2>
        <p className="text-gray-600 mb-4">Все ПУ и загрузки будут удалены. Это действие нельзя отменить!</p>
        <input type="password" placeholder="Код администратора" value={code} onChange={e => setCode(e.target.value)} className="w-full px-3 py-2 border rounded-lg mb-4" />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 bg-gray-100 rounded-lg">Отмена</button>
          <button onClick={() => code && onClear(code)} className="px-4 py-2 bg-red-600 text-white rounded-lg">Очистить</button>
        </div>
      </div>
    </div>
  )
}
