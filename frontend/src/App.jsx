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
  const isEnergoAdmin = user?.role_code === 'ENERGOSERVICE_ADMIN'
  const isLabUser = user?.role_code === 'LAB_USER'
  const canUpload = isLabUser || isSueAdmin
  const canMove = isSueAdmin || isEnergoAdmin
  const canManageUsers = isSueAdmin

  return <AuthContext.Provider value={{ user, loading, login, logout, isSueAdmin, isEnergoAdmin, isLabUser, canUpload, canMove, canManageUsers }}>{children}</AuthContext.Provider>
}

const useAuth = () => useContext(AuthContext)

// ==================== ГЛАВНЫЙ КОМПОНЕНТ ====================
export default function App() {
  return (
    <AuthProvider>
      <Main />
    </AuthProvider>
  )
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
          {page === 'settings' && <SettingsPage />}
        </div>
      </div>
    </div>
  )
}

// ==================== САЙДБАР ====================
function Sidebar({ page, setPage }) {
  const { user, logout, canUpload, canManageUsers } = useAuth()
  const items = [
    { id: 'home', label: '🏠 Главная', show: true },
    { id: 'pu', label: '📦 Приборы учета', show: true },
    { id: 'upload', label: '📤 Загрузка', show: canUpload },
    { id: 'settings', label: '⚙️ Настройки', show: canManageUsers },
  ].filter(i => i.show)

  return (
    <aside className="fixed left-0 top-0 h-full w-56 bg-slate-800 text-white flex flex-col">
      <div className="p-4 border-b border-slate-700 font-bold text-lg">ПУ Система</div>
      <nav className="flex-1 p-3 space-y-1">
        {items.map(i => (
          <button key={i.id} onClick={() => setPage(i.id)} className={`w-full text-left px-3 py-2 rounded-lg ${page === i.id ? 'bg-blue-600' : 'hover:bg-slate-700'}`}>{i.label}</button>
        ))}
      </nav>
      <div className="p-3 border-t border-slate-700">
        <div className="bg-slate-700/50 rounded-lg p-2 mb-2">
          <div className="font-medium truncate">{user?.full_name}</div>
          <div className="text-xs text-slate-400">{user?.unit_name || user?.role_name}</div>
        </div>
        <button onClick={logout} className="w-full px-3 py-2 text-left hover:bg-slate-700 rounded-lg">🚪 Выйти</button>
      </div>
    </aside>
  )
}

function Header() {
  const { user } = useAuth()
  return <header className="h-16 bg-white border-b px-6 flex items-center justify-between sticky top-0"><h1 className="font-semibold">{user?.unit_name || 'Система учета ПУ'}</h1><span className="text-sm text-gray-500">{user?.role_name}</span></header>
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
    try {
      await login(username, password)
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка входа')
    }
    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-800 to-slate-900 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl p-8 w-full max-w-md">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">⚡</div>
          <h1 className="text-2xl font-bold">Система учета ПУ</h1>
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
          <b>Тестовые:</b> admin/admin123, lab/lab123, energo/energo123
        </div>
      </div>
    </div>
  )
}

// ==================== ГЛАВНАЯ СТРАНИЦА ====================
function HomePage({ setPage }) {
  const { user, canUpload, canManageUsers } = useAuth()
  const [stats, setStats] = useState(null)

  useEffect(() => { api.get('/pu/dashboard').then(r => setStats(r.data)) }, [])

  const shortcuts = [
    { id: 'pu', icon: '📦', label: 'Приборы учета', desc: 'Просмотр и управление', show: true },
    { id: 'upload', icon: '📤', label: 'Загрузить реестр', desc: 'Импорт из Excel', show: canUpload },
    { id: 'settings', icon: '⚙️', label: 'Настройки', desc: 'Пользователи', show: canManageUsers },
  ].filter(s => s.show)

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-2xl p-6 text-white">
        <h1 className="text-2xl font-bold">Добро пожаловать, {user?.full_name}!</h1>
        <p className="text-blue-100">{user?.unit_name || user?.role_name}</p>
      </div>

      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <StatCard label="Всего ПУ" value={stats.total_pu} />
          <StatCard label="В ЭСК" value={stats.in_esk} />
          <StatCard label="В РЭС" value={stats.in_res} />
          <StatCard label="Установлено" value={stats.installed} />
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold mb-4">Быстрый доступ</h2>
        <div className="grid grid-cols-3 gap-4">
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

function StatCard({ label, value }) {
  return <div className="bg-white rounded-xl p-5 border"><div className="text-2xl font-bold">{value}</div><div className="text-sm text-gray-500">{label}</div></div>
}

// ==================== СПИСОК ПУ ====================
function PUListPage() {
  const { canMove, isSueAdmin, isEnergoAdmin } = useAuth()
  const [items, setItems] = useState([])
  const [units, setUnits] = useState([])
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [unitFilter, setUnitFilter] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [selected, setSelected] = useState([])
  const [moveModal, setMoveModal] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => { api.get('/units').then(r => setUnits(r.data)) }, [])
  useEffect(() => { load() }, [page, status, unitFilter])

  const load = async () => {
    setLoading(true)
    const r = await api.get('/pu/items', { params: { page, search: search || undefined, status: status || undefined, unit_id: unitFilter || undefined } })
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

  const statusLabels = { NEW: 'Новый', IN_ESK: 'В ЭСК', IN_RES: 'В РЭС', INSTALLED: 'Установлен', DEFECT: 'Брак' }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div><h1 className="text-2xl font-bold">Приборы учета</h1><p className="text-gray-500">Всего: {total}</p></div>
        <button onClick={load} className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200">🔄 Обновить</button>
      </div>

      <div className="bg-white rounded-xl border p-4 flex gap-3">
        <input type="text" placeholder="Поиск по серийному номеру..." value={search} onChange={e => setSearch(e.target.value)} className="flex-1 px-3 py-2 border rounded-lg" />
        <button onClick={() => { setPage(1); load() }} className="px-4 py-2 bg-blue-600 text-white rounded-lg">Найти</button>
        <select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }} className="px-3 py-2 border rounded-lg">
          <option value="">Все статусы</option>
          {Object.entries(statusLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        {(isSueAdmin || isEnergoAdmin) && (
          <select value={unitFilter} onChange={e => { setUnitFilter(e.target.value); setPage(1) }} className="px-3 py-2 border rounded-lg">
            <option value="">Все подразделения</option>
            {units.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        )}
      </div>

      {selected.length > 0 && canMove && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-center justify-between">
          <span className="text-blue-700 font-medium">Выбрано: {selected.length}</span>
          <div className="flex gap-2">
            <button onClick={() => setMoveModal(true)} className="px-4 py-2 bg-blue-600 text-white rounded-lg">➡️ Переместить</button>
            <button onClick={() => setSelected([])} className="px-4 py-2 bg-gray-100 rounded-lg">Отменить</button>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border overflow-hidden">
        {loading ? <div className="p-8 text-center">Загрузка...</div> : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                {canMove && <th className="w-10 px-4 py-3"></th>}
                <th className="px-4 py-3 text-left">Серийный номер</th>
                <th className="px-4 py-3 text-left">Тип</th>
                <th className="px-4 py-3 text-left">Подразделение</th>
                <th className="px-4 py-3 text-left">Статус</th>
                <th className="px-4 py-3 text-left">Дата</th>
              </tr>
            </thead>
            <tbody>
              {items.map(i => (
                <tr key={i.id} className="border-t hover:bg-gray-50">
                  {canMove && <td className="px-4 py-3"><input type="checkbox" checked={selected.includes(i.id)} onChange={() => setSelected(s => s.includes(i.id) ? s.filter(x => x !== i.id) : [...s, i.id])} /></td>}
                  <td className="px-4 py-3 font-mono">{i.serial_number}</td>
                  <td className="px-4 py-3 text-gray-600 max-w-xs truncate">{i.pu_type || '—'}</td>
                  <td className="px-4 py-3">{i.current_unit_name || '—'}</td>
                  <td className="px-4 py-3"><span className={`px-2 py-1 rounded-full text-xs ${i.status === 'IN_ESK' ? 'bg-yellow-100 text-yellow-800' : i.status === 'IN_RES' ? 'bg-blue-100 text-blue-800' : i.status === 'INSTALLED' ? 'bg-green-100 text-green-800' : 'bg-gray-100'}`}>{statusLabels[i.status]}</span></td>
                  <td className="px-4 py-3 text-gray-500">{i.uploaded_at ? new Date(i.uploaded_at).toLocaleDateString('ru') : '—'}</td>
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

      {moveModal && <MoveModal units={units} onClose={() => setMoveModal(false)} onMove={handleMove} count={selected.length} />}
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

// ==================== НАСТРОЙКИ (ПОЛЬЗОВАТЕЛИ) ====================
function SettingsPage() {
  const { canManageUsers } = useAuth()
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState([])
  const [units, setUnits] = useState([])
  const [modal, setModal] = useState(null)

  useEffect(() => {
    api.get('/users').then(r => setUsers(r.data))
    api.get('/roles').then(r => setRoles(r.data))
    api.get('/units').then(r => setUnits(r.data))
  }, [])

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

  if (!canManageUsers) return <div className="text-center py-12 text-gray-500">Нет доступа</div>

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Пользователи</h1>
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

      {modal && <UserModal user={modal.user} roles={roles} units={units} onClose={() => setModal(null)} onSave={handleSave} />}
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
