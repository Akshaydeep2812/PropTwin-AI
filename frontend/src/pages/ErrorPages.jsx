import { Component } from "react";
import { Link } from "react-router-dom";

function Message({ code, title, children }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 text-center">
      <p className="tabular text-sm font-semibold text-teal-700">{code}</p>
      <h1 className="mt-2 text-3xl font-semibold text-navy-900">{title}</h1>
      <div className="mt-3 max-w-md text-sm text-slate-600">{children}</div>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <Message code="404" title="Page not found">
      <p>This page does not exist, or you do not have access to it.</p>
      <Link to="/" className="mt-4 inline-block font-medium text-teal-700 underline">
        Go to the home page
      </Link>
    </Message>
  );
}

/** Shows a recoverable page instead of a blank screen if a page crashes while rendering. */
export class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.error("Page render failed", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <Message code="Error" title="Something went wrong">
        <p>This page could not be displayed. Your data has not been changed.</p>
        <button type="button" onClick={() => window.location.assign("/")} className="mt-4 font-medium text-teal-700 underline">
          Reload the application
        </button>
      </Message>
    );
  }
}
