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
            {/* Desktop Navigation */}
            <nav className="hidden md:block nav-desktop">
                <div className="nav-desktop__inner">
                    <Link to="/" className="nav-logo">
                        <div className="nav-logo__icon">
                            <Dumbbell className="w-5 h-5 text-black" />
                        </div>
                        <span className="nav-logo__text">Helf</span>
                    </Link>

                    <div className="nav-links">
                        {navItems.map(({ path, label, icon: Icon }) => (
                            <Link
                                key={path}
                                to={path}
                                className={`nav-link ${isActive(path) ? 'nav-link--active' : ''}`}
                            >
                                <Icon className="w-[18px] h-[18px]" />
                                {label}
                            </Link>
                        ))}
                    </div>
                </div>
            </nav>

            <div className="hidden md:block nav-spacer-desktop" />

            {/* Mobile Navigation */}
            <nav className="md:hidden nav-mobile">
                <div className="nav-mobile__inner">
                    {navItems.map(({ path, label, icon: Icon }) => (
                        <Link
                            key={path}
                            to={path}
                            className={`nav-mobile-link ${isActive(path) ? 'nav-mobile-link--active' : ''}`}
                        >
                            <div className="nav-mobile-link__icon">
                                <Icon className="w-[22px] h-[22px]" />
                            </div>
                            <span className="nav-mobile-link__label">{label}</span>
                        </Link>
                    ))}
                </div>
            </nav>

            <div className="md:hidden nav-spacer-mobile" />
        </>
    );
};

export default Navigation;
