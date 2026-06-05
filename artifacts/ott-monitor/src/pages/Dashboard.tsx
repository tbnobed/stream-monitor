import React from "react";
import { useListDevices, useListHlsStreams, useGetDashboardSummary } from "@workspace/api-client-react";
import { useSse } from "@/hooks/use-sse";
import { WebRtcPlayer } from "@/components/WebRtcPlayer";
import { PlatformIcon } from "@/components/PlatformIcon";
import { StatusBadge } from "@/components/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GuacamolePanel } from "@/components/GuacamolePanel";

export default function Dashboard() {
  const { data: summary } = useGetDashboardSummary({ query: { refetchInterval: 15000 } });
  const { data: devices } = useListDevices({ query: { refetchInterval: 15000 } });
  const { data: hlsStreams } = useListHlsStreams({ query: { refetchInterval: 15000 } });
  const { deviceStatuses, hlsStreamStatuses } = useSse();

  return (
    <div className="p-4 space-y-4 max-w-full">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Total Devices</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary?.total_devices || 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-status-down/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-status-down uppercase tracking-wider">Devices Down</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-status-down animate-pulse">{summary?.devices_down || 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Total HLS</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary?.total_hls_streams || 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-status-down/50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-status-down uppercase tracking-wider">HLS Down</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-status-down animate-pulse">{summary?.hls_down || 0}</div>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="devices" className="w-full relative">
        <div className="flex justify-between items-center mb-4">
          <TabsList className="grid w-[400px] grid-cols-2 bg-muted">
            <TabsTrigger value="devices" className="data-[state=active]:bg-background">Devices</TabsTrigger>
            <TabsTrigger value="hls" className="data-[state=active]:bg-background">Source Streams</TabsTrigger>
          </TabsList>
        </div>
        
        <TabsContent value="devices" className="mt-0">
          <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {devices?.map((device) => {
              const liveStatus = deviceStatuses[device.id]?.status || device.current_status;
              const isDown = liveStatus === 'DOWN';
              return (
                <Card key={device.id} className={`bg-card overflow-hidden border ${isDown ? 'border-status-down shadow-[0_0_15px_rgba(255,0,0,0.2)]' : 'border-border'}`}>
                  <CardHeader className="p-3 bg-secondary/50 border-b flex flex-row items-center justify-between space-y-0">
                    <div className="flex items-center space-x-2 truncate">
                      <PlatformIcon platform={device.platform} className="h-4 w-4 shrink-0 text-primary" />
                      <span className="font-bold text-sm truncate" title={device.name}>{device.name}</span>
                    </div>
                    <StatusBadge status={liveStatus} className="shrink-0" />
                  </CardHeader>
                  <CardContent className="p-0 flex flex-col">
                    <div className="aspect-video bg-black relative">
                      {device.enabled ? (
                        <WebRtcPlayer streamKey={device.srs_stream_key} className="w-full h-full" />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center text-muted-foreground text-xs uppercase tracking-widest">
                          Disabled
                        </div>
                      )}
                    </div>
                    <div className="p-2 text-[10px] text-muted-foreground flex justify-between items-center border-t border-border/50 bg-secondary/20 font-mono">
                      <span className="truncate max-w-[200px]" title={device.srs_stream_key}>{device.srs_stream_key}</span>
                      <span>{device.last_checked_at ? new Date(device.last_checked_at).toLocaleTimeString() : 'N/A'}</span>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </TabsContent>
        <TabsContent value="hls" className="mt-0">
          <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {hlsStreams?.map((stream) => {
              const liveStatus = hlsStreamStatuses[stream.id]?.status || stream.current_status;
              const isDown = liveStatus === 'DOWN';
              return (
                <Card key={stream.id} className={`bg-card border ${isDown ? 'border-status-down shadow-[0_0_15px_rgba(255,0,0,0.2)]' : 'border-border'}`}>
                   <CardHeader className="p-4 flex flex-row items-start justify-between space-y-0">
                      <div className="overflow-hidden pr-2">
                        <CardTitle className="text-base font-bold mb-1 truncate" title={stream.name}>{stream.name}</CardTitle>
                        <div className="text-xs text-muted-foreground truncate w-full" title={stream.master_url}>{stream.master_url}</div>
                      </div>
                      <StatusBadge status={liveStatus} className="shrink-0" />
                   </CardHeader>
                   <CardContent className="p-4 pt-0">
                      <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                        <div className="bg-secondary/50 p-2 rounded">
                          <div className="text-muted-foreground mb-1 uppercase tracking-wider text-[10px]">Renditions</div>
                          <div className="font-mono text-foreground font-medium">{stream.expected_renditions || 'Any'}</div>
                        </div>
                        <div className="bg-secondary/50 p-2 rounded">
                          <div className="text-muted-foreground mb-1 uppercase tracking-wider text-[10px]">Encrypted</div>
                          <div className="font-mono text-foreground font-medium">{stream.is_encrypted ? 'Yes' : 'No'}</div>
                        </div>
                      </div>
                   </CardContent>
                </Card>
              );
            })}
          </div>
        </TabsContent>
      </Tabs>
      
      <GuacamolePanel />
    </div>
  );
}
