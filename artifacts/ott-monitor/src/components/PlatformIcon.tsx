import React from 'react';
import { SiRoku, SiGooglecast, SiAppletv } from 'react-icons/si';
import { Monitor, Flame } from 'lucide-react';
import type { DevicePlatform } from '@workspace/api-client-react';

export function PlatformIcon({ platform, className }: { platform: DevicePlatform | string, className?: string }) {
  switch (platform.toLowerCase()) {
    case 'roku': return <SiRoku className={className} />;
    case 'firetv': return <Flame className={className} />;
    case 'chromecast': return <SiGooglecast className={className} />;
    case 'appletv': return <SiAppletv className={className} />;
    default: return <Monitor className={className} />;
  }
}
