import { Link, useLocation } from "react-router-dom";
import { Calendar, TrendingUp, Weight, ListTodo, Dumbbell } from "lucide-react";

const Navigation = () => {
    const location = useLocation();

    const isActive = (path: string) => {
        if (path === "/" && location.pathname === "/") return true;
        if (path !== "/" && location.pathname.startsWith(path)) return true;
        return false;
    };

    const navItems = [
        { path: "/", label: "Calendar", icon: Calendar },
        { path: "/progression", label: "Progress", icon: TrendingUp },
        { path: "/body-composition", label: "Composition", icon: Weight },
        { path: "/upcoming", label: "Upcoming", icon: ListTodo },
    ];

    return (
        <>
            {/* Desktop Navigation - Fixed Horizontal Top */}
            <nav
                className="hidden md:block fixed top-0 left-0 right-0"
                style={{
                    background: 'rgba(10, 10, 11, 0.8)',
                    backdropFilter: 'blur(12px)',
                    borderBottom: '1px solid var(--border-subtle)',
                    height: '60px',
                    zIndex: 100,
                }}
            >
                <div className="max-w-7xl mx-auto h-full flex items-center justify-between px-6">
                    {/* Logo - Top Left (links to homepage) */}
                    <Link
                        to="/"
                        className="flex items-center gap-3 transition-opacity"
                        style={{
                            opacity: 1,
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.opacity = '0.8'}
                        onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
                    >
                        <div
                            style={{
                                width: '32px',
                                height: '32px',
                                borderRadius: '8px',
                                background: 'var(--accent)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                            }}
                        >
                            <Dumbbell style={{ width: '18px', height: '18px', color: '#000' }} />
                        </div>
                        <span
                            style={{
                                fontFamily: 'var(--font-display)',
                                fontSize: '18px',
                                fontWeight: 700,
                                color: 'var(--text-primary)',
                                letterSpacing: '-0.01em',
                            }}
                        >
                            Helf
                        </span>
                    </Link>

                    {/* Navigation Links - Clear & Brief */}
                    <div className="flex items-center gap-1">
                        {navItems.map(({ path, label, icon: Icon }) => {
                            const active = isActive(path);
                            return (
                                <Link
                                    key={path}
                                    to={path}
                                    className="flex items-center gap-2 transition-all"
                                    style={{
                                        padding: '8px 16px',
                                        borderRadius: '8px',
                                        color: active ? '#000' : 'var(--text-secondary)',
                                        background: active ? 'var(--accent)' : 'transparent',
                                        fontSize: '14px',
                                        fontWeight: active ? 600 : 500,
                                        transitionDuration: 'var(--duration-normal)',
                                    }}
                                    onMouseEnter={(e) => {
                                        if (!active) {
                                            e.currentTarget.style.background = 'var(--bg-hover)';
                                            e.currentTarget.style.color = 'var(--text-primary)';
                                        }
                                    }}
                                    onMouseLeave={(e) => {
                                        if (!active) {
                                            e.currentTarget.style.background = 'transparent';
                                            e.currentTarget.style.color = 'var(--text-secondary)';
                                        }
                                    }}
                                >
                                    <Icon style={{ width: '18px', height: '18px' }} />
                                    {label}
                                </Link>
                            );
                        })}
                    </div>
                </div>
            </nav>

            {/* Desktop - Add padding to prevent content from hiding under fixed nav */}
            <div className="hidden md:block" style={{ height: '60px' }} />

            {/* Mobile - Hamburger/Bottom Hybrid */}
            <nav
                className="md:hidden fixed bottom-0 left-0 right-0"
                style={{
                    background: 'rgba(20, 20, 22, 0.95)',
                    backdropFilter: 'blur(12px)',
                    borderTop: '1px solid var(--border-subtle)',
                    paddingBottom: 'env(safe-area-inset-bottom)',
                    zIndex: 100,
                }}
            >
                <div className="grid grid-cols-4" style={{ height: '64px' }}>
                    {navItems.map(({ path, label, icon: Icon }) => {
                        const active = isActive(path);
                        return (
                            <Link
                                key={path}
                                to={path}
                                className="flex flex-col items-center justify-center gap-1 transition-all"
                                style={{
                                    color: active ? 'var(--accent)' : 'var(--text-muted)',
                                    transitionDuration: 'var(--duration-normal)',
                                }}
                            >
                                <div
                                    style={{
                                        width: '40px',
                                        height: '40px',
                                        borderRadius: '10px',
                                        background: active ? 'var(--accent-subtle)' : 'transparent',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        transition: 'all var(--duration-normal)',
                                    }}
                                >
                                    <Icon style={{
                                        width: '22px',
                                        height: '22px',
                                    }} />
                                </div>
                                <span
                                    style={{
                                        fontSize: '10px',
                                        fontWeight: active ? 600 : 500,
                                    }}
                                >
                                    {label}
                                </span>
                            </Link>
                        );
                    })}
                </div>
            </nav>

            {/* Mobile - Bottom padding for fixed nav */}
            <div className="md:hidden" style={{ height: '64px' }} />
        </>
    );
};

export default Navigation;
