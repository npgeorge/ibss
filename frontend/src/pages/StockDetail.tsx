import React from 'react';
import { useParams } from 'react-router-dom';

const StockDetail: React.FC = () => {
  const { symbol } = useParams<{ symbol: string }>();

  return (
    <div className="stock-detail">
      <h2>{symbol}</h2>

      <div className="card">
        <h3>Stock Profile</h3>
        <p>Loading stock details...</p>
      </div>

      <div className="card">
        <h3>Technical Analysis</h3>
        <p>Chart will be displayed here</p>
      </div>

      <div className="card">
        <h3>Magic Line Information</h3>
        <p>Magic Line: 10-week SMA</p>
        <p>Current Distance: +2.5%</p>
      </div>

      <div className="card">
        <h3>Insider Activity</h3>
        <p>Loading insider transactions...</p>
      </div>
    </div>
  );
};

export default StockDetail;
