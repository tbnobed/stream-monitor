import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider, QueryCache } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { getGetCurrentUserQueryKey } from "@workspace/api-client-react";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Layout } from "@/components/Layout";
import { AuthProvider, useAuth } from "@/hooks/use-auth";
import Dashboard from "@/pages/Dashboard";
import Devices from "@/pages/Devices";
import HlsStreams from "@/pages/HlsStreams";
import Incidents from "@/pages/Incidents";
import Settings from "@/pages/Settings";
import Users from "@/pages/Users";
import Login from "@/pages/Login";
import MobileRemote from "@/pages/MobileRemote";
import NotFound from "@/pages/not-found";

function statusOf(error: unknown): number | undefined {
  return (error as { status?: number })?.status;
}

function urlOf(error: unknown): string | undefined {
  return (error as { url?: string })?.url;
}

// When any query returns 401 (session expired), re-check the current user so the
// app falls back to the login screen instead of showing a broken page.
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      const url = urlOf(error);
      if (statusOf(error) === 401 && url && !url.includes("/auth/me")) {
        queryClient.invalidateQueries({ queryKey: getGetCurrentUserQueryKey() });
      }
    },
  }),
  defaultOptions: {
    queries: {
      retry: (count, error) => {
        const status = statusOf(error);
        if (status && status >= 400 && status < 500) return false;
        return count < 2;
      },
    },
  },
});

function Router() {
  const { isAdmin } = useAuth();
  return (
    <Layout>
      <Switch>
        <Route path="/" component={Dashboard} />
        {isAdmin && <Route path="/devices" component={Devices} />}
        {isAdmin && <Route path="/hls-streams" component={HlsStreams} />}
        {isAdmin && <Route path="/incidents" component={Incidents} />}
        {isAdmin && <Route path="/settings" component={Settings} />}
        {isAdmin && <Route path="/users" component={Users} />}
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}

function AuthGate() {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  return <Router />;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <Switch>
            {/* Public phone remote — opened via QR, no login session. */}
            <Route path="/m/:token">
              {(params) => <MobileRemote token={params.token} />}
            </Route>
            {/* Everything else requires authentication. */}
            <Route>
              <AuthProvider>
                <AuthGate />
              </AuthProvider>
            </Route>
          </Switch>
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
