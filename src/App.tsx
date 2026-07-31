import { useEffect } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import Header from './components/Header'
import Footer from './components/Footer'
import Home from './pages/Home'
import DownloadPage from './pages/Download'
import Features from './pages/Features'
import Pricing from './pages/Pricing'
import Support from './pages/Support'
import Odeme from './pages/Odeme'
import { LegalPage } from './pages/Legal'
import NotFound from './pages/NotFound'
import { LEGAL_DOCS } from './config'
import { AuthProvider } from './context/AuthContext'
import { AuthModalProvider } from './context/AuthModal'

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

export default function App() {
  return (
    <AuthProvider>
      <AuthModalProvider>
        <div className="flex min-h-svh flex-col">
          <ScrollToTop />
          <Header />
          <main className="flex-1">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/download" element={<DownloadPage />} />
              <Route path="/features" element={<Features />} />
              <Route path="/pricing" element={<Pricing />} />
              <Route path="/odeme" element={<Odeme />} />
              <Route path="/support" element={<Support />} />
              {LEGAL_DOCS.map((d) => (
                <Route key={d.slug} path={`/${d.slug}`} element={<LegalPage />} />
              ))}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </main>
          <Footer />
        </div>
      </AuthModalProvider>
    </AuthProvider>
  )
}
