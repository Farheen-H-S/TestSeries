import { useParams } from 'react-router-dom';

const Processing = () => {
  const { documentId } = useParams();

  return (
    <div className="container">
      <h2>Processing Paper</h2>
      <p style={{ marginTop: '1rem', color: 'var(--text-secondary)' }}>
        Checking status for Document #{documentId}...
      </p>
    </div>
  );
};

export default Processing;
