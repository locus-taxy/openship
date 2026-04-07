"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { AlertTriangle } from "lucide-react"
import L from "leaflet"
import "leaflet/dist/leaflet.css";
import { Button } from "@/components/ui/button"
import { Loader2 } from "lucide-react"
// https://tomickigrzegorz.github.io/leaflet-examples/#

const MapComponent = ({ locations }: { locations: AccidentLocation[] }) => {
  useEffect(() => {
    const config = {
        minZoom: 7,
        maxZoom: 18,
      };
      const zoom = 12; // A bit zoomed out to see multiple markers

      // Default coordinates (only used if no locations are provided)
      const defaultLat = 12.925795662008651;
      const defaultLng = 77.63697162832435;

      // Get center coordinates from the first location or use defaults
      const centerLat = locations.length > 0 ? locations[0].lat_lng.lat : defaultLat;
      const centerLng = locations.length > 0 ? locations[0].lat_lng.lng : defaultLng;

      const map = L.map("map", config).setView([centerLat, centerLng], zoom);

      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map);

      // Add markers for all locations
     locations.map(location => {
        const marker = L.circleMarker([location.lat_lng.lat, location.lat_lng.lng], {
            radius: 8,
            fillColor: '#ff3300',  // Red color for accidents
            color: '#00',         // Black border
            weight: 1,             // Border width
            opacity: 1,
            fillOpacity: 0.8
          }).addTo(map);

          // Add a pulsing effect class if you want
          marker.getElement()?.classList.add('pulse-marker');

        // Add popup with location details
        marker.bindPopup(`
          <strong>${location.title}</strong><br>
          ${location.description}<br>
          <small>Date: ${location.date}</small>
        `);

        return marker;
      });

      // If we have locations, fit the map to show all markers
      if (locations.length > 0) {
        // Create a bounds object
        const bounds = L.latLngBounds(
          locations.map(loc => [loc.lat_lng.lat, loc.lat_lng.lng])
        );

        // Adjust the map view to fit all markers
        map.fitBounds(bounds, { padding: [50, 50] });
      }

      return () => {
        map.remove();
      };


  }, [locations]);

  return <div id="map" style={{ width: "100%", height: "500px" }}></div>;
};


// Define the accident location type
export interface AccidentLocation {
  id: string | number
  lat_lng: {
    lat: number
    lng: number
  }
  title?: string
  description?: string
  date?: string
}

interface AccidentMapProps {
  locations: AccidentLocation[]
  fetchEvents: () => void,
  isLoadingEvents: boolean,
  initialCenter?: [number, number]
  initialZoom?: number
  height?: string
  title?: string
  description?: string
}

export default function AccidentMap({
    locations = [],
    fetchEvents,
    isLoadingEvents,
    height = "600px",
    title = "Accident Map",
    description = "Map showing accident locations",
}: AccidentMapProps) {
  const [isMounted, setIsMounted] = useState(false)

  // Custom accident marker icon

  // Handle client-side only rendering
  useEffect(() => {
    setIsMounted(true)
  }, [])

  if (!isMounted) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <div style={{ height }} className="flex items-center justify-center bg-muted">
            Loading map...
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
        <div>
            <Button onClick={fetchEvents} variant="outline" disabled={isLoadingEvents} className="mt-2">
                {isLoadingEvents ? <Loader2 className="h-4 w-4 animate-spin" /> : "Fetch Events"}
            </Button>
        </div>
      </CardHeader>

      <CardContent>
        {locations.length === 0 ? (
          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>No accident data</AlertTitle>
            <AlertDescription>There are no accident locations to display on the map.</AlertDescription>
          </Alert>
        ) : (
          <div style={{ height }} className="w-full rounded-md overflow-hidden">
            <MapComponent locations={locations} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}

