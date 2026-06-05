import React from 'react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { DeviceCurrentStatus, HlsStreamCurrentStatus } from '@workspace/api-client-react';

export type StatusType = DeviceCurrentStatus | HlsStreamCurrentStatus | 'UNKNOWN';

interface StatusBadgeProps {
  status?: StatusType;
  className?: string;
  animate?: boolean;
}

export function StatusBadge({ status = 'UNKNOWN', className, animate = true }: StatusBadgeProps) {
  const getStatusColor = (s: StatusType) => {
    switch (s) {
      case 'HEALTHY':
        return 'bg-status-healthy text-status-healthy-foreground border-status-healthy/20';
      case 'WARNING':
        return 'bg-status-warning text-status-warning-foreground border-status-warning/20';
      case 'DOWN':
        return 'bg-status-down text-status-down-foreground border-status-down/20';
      default:
        return 'bg-status-unknown text-status-unknown-foreground border-status-unknown/20';
    }
  };

  const getDotColor = (s: StatusType) => {
    switch (s) {
      case 'HEALTHY': return 'bg-white';
      case 'WARNING': return 'bg-white';
      case 'DOWN': return 'bg-white';
      default: return 'bg-white';
    }
  };

  return (
    <Badge 
      variant="outline" 
      className={cn(
        'font-mono text-xs px-2.5 py-0.5 border shadow-sm transition-colors duration-300', 
        getStatusColor(status),
        status === 'DOWN' && animate && 'animate-pulse',
        className
      )}
    >
      <span className={cn('mr-1.5 h-1.5 w-1.5 rounded-full inline-block', getDotColor(status))} />
      {status}
    </Badge>
  );
}
